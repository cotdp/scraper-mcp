"""Credential boundary regressions using only synthetic proxies and mocked HTTP."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import traceback
from dataclasses import asdict
from datetime import timedelta
from urllib.parse import quote, quote_plus

import pytest
import requests
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request

from scraper_mcp.admin import service as admin_service
from scraper_mcp.admin.router import api_request_details
from scraper_mcp.cache_manager import CacheManager
from scraper_mcp.metrics import ServerMetrics
from scraper_mcp.providers import RequestsProvider, ScrapeResult
from scraper_mcp.resources.cache import register_cache_resources
from scraper_mcp.tools import router, service

TARGET = "https://example.com/articles/page?source=test"
API_KEY = "synthetic-scrapeops/key+token"
PROXY_USER = "synthetic-proxy-user"
PROXY_PASSWORD = "synthetic-proxy/password+token"
PROXY_URL = f"http://{PROXY_USER}:{quote(PROXY_PASSWORD, safe='')}@proxy.example:8080"
TOOLS = [
    router.scrape_url,
    router.scrape_url_html,
    router.scrape_url_text,
    router.scrape_extract_links,
]


def assert_no_credentials(value):
    text = str(value)
    for credential in (API_KEY, PROXY_USER, PROXY_PASSWORD):
        for form in (credential, quote(credential, safe=""), quote_plus(credential)):
            assert form not in text


@pytest.fixture
def proxy_boundary(monkeypatch, tmp_path):
    monkeypatch.setenv("SCRAPEOPS_API_KEY", API_KEY)
    monkeypatch.setattr(
        admin_service,
        "_runtime_config",
        {"proxy_enabled": True, "http_proxy": PROXY_URL, "https_proxy": PROXY_URL},
    )
    metrics = ServerMetrics()
    monkeypatch.setattr("scraper_mcp.metrics._metrics", metrics)
    with CacheManager(cache_dir=tmp_path / "cache") as cache:
        monkeypatch.setattr("scraper_mcp.cache_manager._cache_manager", cache)
        provider = RequestsProvider(max_retries=0, retry_delay=0)
        provider.session.trust_env = False
        monkeypatch.setattr(service, "get_provider", lambda *args: provider)
        yield provider, cache, metrics
        provider.session.close()


def response_for(url, *, reflect_credentials=False):
    response = requests.Response()
    response.url = url
    response.status_code = 200
    response.headers["content-type"] = "text/html"
    response.headers["Server"] = "test-server"
    response.elapsed = timedelta(milliseconds=25)
    html = '<html><title>Example</title><body><a href="child">Child</a></body></html>'
    if reflect_credentials:
        response.headers["X-Transport-URL"] = url
        response.headers["X-Proxy"] = PROXY_URL
        html += f"<p>{API_KEY} {quote_plus(API_KEY)} {PROXY_PASSWORD}</p>"
    response._content = html.encode()
    return response


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("scrapeops", [False, True])
async def test_results_cache_and_logs_exclude_credentials(
    proxy_boundary, monkeypatch, caplog, tool, scrapeops
):
    provider, cache, metrics = proxy_boundary
    provider.scrapeops_enabled = scrapeops
    transport_url = provider._build_scrapeops_url(TARGET) if scrapeops else TARGET
    response = response_for(transport_url, reflect_credentials=True)
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        assert url == transport_url
        assert kwargs["proxies"] == {"http": PROXY_URL, "https": PROXY_URL}
        return response

    monkeypatch.setattr(provider.session, "get", get)
    caplog.set_level(logging.DEBUG)
    fresh = await tool([TARGET], include_headers=True, max_retries=0)
    cached = await tool([TARGET], include_headers=True, max_retries=0)
    assert fresh.successful == cached.successful == 1
    assert fresh.results[0].url == cached.results[0].url == TARGET
    assert len(calls) == 1
    if tool is router.scrape_extract_links:
        assert fresh.results[0].data.links[0]["url"] == "https://example.com/articles/child"
    else:
        assert fresh.results[0].data.content_type == "text/html"
        assert fresh.results[0].data.metadata["proxy_used"] is True
        assert "proxy_config" not in fresh.results[0].data.metadata
        assert fresh.results[0].data.metadata["headers"]["Server"] == "test-server"
        assert cached.results[0].data.metadata["from_cache"] is True

    stored = cache.get(metrics.recent_requests[-1].cache_key)
    assert stored.url == TARGET
    mcp = FastMCP("credential-boundary")
    router.register_scraping_tools(mcp)
    register_cache_resources(mcp)
    serialized = await mcp.call_tool(
        tool.__name__, {"urls": [TARGET], "include_headers": True, "max_retries": 0}
    )
    request_id = metrics.recent_requests[-1].request_id
    resource = await mcp.read_resource(f"cache://request/{request_id}")
    details = await api_request_details(
        Request({"type": "http", "path_params": {"request_id": request_id}})
    )
    for output in (
        fresh.model_dump_json(),
        cached.model_dump_json(),
        asdict(stored),
        metrics,
        caplog.text,
        serialized,
        resource,
        details.body,
    ):
        assert_no_credentials(output)
    cache.close()
    for path in cache.cache_dir.iterdir():
        if path.is_file():
            blob = path.read_bytes()
            for credential in (API_KEY, PROXY_USER, PROXY_PASSWORD):
                assert credential.encode() not in blob
                assert quote(credential, safe="").encode() not in blob


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("scrapeops", [False, True])
@pytest.mark.parametrize(
    "error_type",
    [
        requests.HTTPError,
        requests.Timeout,
        requests.exceptions.ProxyError,
        requests.exceptions.TooManyRedirects,
        requests.exceptions.InvalidURL,
    ],
)
async def test_errors_do_not_expose_transport_credentials(
    proxy_boundary, monkeypatch, caplog, tool, error_type, scrapeops
):
    provider, cache, metrics = proxy_boundary
    provider.scrapeops_enabled = scrapeops
    transport_url = provider._build_scrapeops_url(TARGET) if scrapeops else TARGET
    response = response_for(transport_url)
    response.status_code = 502
    prepared = requests.Request("GET", transport_url).prepare()
    original_error = error_type(
        f"Failed for {transport_url} through {PROXY_URL}", request=prepared, response=response
    )
    calls = []

    def get(*args, **kwargs):
        calls.append(args[0])
        raise original_error

    monkeypatch.setattr(provider.session, "get", get)
    caplog.set_level(logging.DEBUG)
    with pytest.raises(error_type) as caught:
        await provider.scrape(TARGET, max_retries=1)
    assert_no_credentials(str(caught.value))
    assert_no_credentials("".join(traceback.format_exception(caught.value)))
    assert caught.value.request is None
    assert caught.value.response is None
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None
    assert TARGET in str(caught.value)
    retryable = issubclass(
        error_type, (requests.HTTPError, requests.Timeout, requests.ConnectionError)
    )
    assert len(calls) == (2 if retryable else 1)

    result = await tool([TARGET], max_retries=0)
    assert result.failed == 1
    assert error_type.__name__ in result.results[0].error
    assert TARGET in result.results[0].error
    assert len(cache.cache) == 0
    for output in (result.model_dump_json(), metrics, caplog.text):
        assert_no_credentials(output)


@pytest.mark.parametrize("legacy_kind", ["proxy_config", "scrapeops_url"])
async def test_legacy_unsafe_cache_is_not_returned(proxy_boundary, monkeypatch, legacy_kind):
    provider, cache, _metrics = proxy_boundary
    provider.scrapeops_enabled = False
    key = cache.generate_cache_key(TARGET, headers={"User-Agent": provider.user_agent})
    legacy = ScrapeResult(
        url=provider._build_scrapeops_url(TARGET) if legacy_kind == "scrapeops_url" else TARGET,
        content="<p>Legacy result</p>",
        status_code=200,
        content_type="text/html",
        metadata={"proxy_used": True, "proxy_config": {"http": PROXY_URL}}
        if legacy_kind == "proxy_config"
        else {},
    )
    cache.set(key, legacy)
    assert cache.get(key) is None
    assert cache.get(key, default="unavailable") == "unavailable"
    calls = []

    def get(*args, **kwargs):
        calls.append(args[0])
        return response_for(TARGET)

    monkeypatch.setattr(provider.session, "get", get)
    result = await provider.scrape(TARGET)
    assert calls == [TARGET]
    assert result.url == TARGET
    assert_no_credentials(asdict(result))
    assert_no_credentials(asdict(cache.get(key)))


def test_proxy_startup_log_omits_endpoints(tmp_path):
    script = (
        "import logging; logging.basicConfig(level=logging.DEBUG); import scraper_mcp.admin.service"
    )
    result = subprocess.run(  # noqa: S603 — fixed interpreter/script and synthetic environment.
        [sys.executable, "-c", script],
        env={
            "PATH": os.defpath,
            "HTTP_PROXY": PROXY_URL,
            "HTTPS_PROXY": PROXY_URL,
            "CACHE_DIR": str(tmp_path / "cache"),
        },
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert "Proxy enabled" in result.stderr
    assert_no_credentials(result.stdout + result.stderr)


def test_metadata_cleaner_omits_proxy_config():
    result = service.clean_metadata({"proxy_used": True, "proxy_config": {"http": PROXY_URL}})
    assert result == {"proxy_used": True}


def test_direct_scrapeops_homepage_cache_is_preserved(proxy_boundary):
    _provider, cache, _metrics = proxy_boundary
    result = ScrapeResult(
        url="https://proxy.scrapeops.io/",
        content="Public homepage",
        status_code=200,
        content_type="text/html",
        metadata={},
    )
    cache.set("homepage", result)
    assert cache.get("homepage") == result
