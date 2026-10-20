"""Certificate verification is the default from resources through HTTP requests."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
import requests

from scraper_mcp.admin import service as admin_service
from scraper_mcp.admin.service import get_config, get_current_config
from scraper_mcp.providers.requests_provider import RequestsProvider
from scraper_mcp.resources.config import DEFAULT_CONFIG


def test_configuration_defaults_verify_certificates() -> None:
    assert get_config("verify_ssl") is True
    assert get_current_config()["defaults"]["verify_ssl"] is True
    assert DEFAULT_CONFIG["verify_ssl"] is True


@pytest.mark.asyncio
async def test_outbound_https_verifies_certificates_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SCRAPEOPS_API_KEY", raising=False)
    response = Mock()
    response.url = "https://example.com"
    response.text = "<p>Verified</p>"
    response.status_code = 200
    response.headers = {"Content-Type": "text/html"}
    response.elapsed.total_seconds.return_value = 0.01
    get = Mock(return_value=response)
    provider = RequestsProvider(cache_enabled=False)
    monkeypatch.setattr(provider.session, "get", get)
    await provider.scrape("https://example.com")
    assert get.call_args.kwargs["verify"] is True


@pytest.mark.asyncio
async def test_enabling_tls_verification_does_not_reuse_unverified_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SCRAPEOPS_API_KEY", raising=False)
    monkeypatch.setattr(admin_service, "_runtime_config", {"verify_ssl": False})
    response = Mock()
    response.url = "https://example.com"
    response.text = "<p>Previously unverified</p>"
    response.status_code = 200
    response.headers = {"Content-Type": "text/html"}
    response.elapsed.total_seconds.return_value = 0.01
    get = Mock(return_value=response)
    provider = RequestsProvider(max_retries=0)
    monkeypatch.setattr(provider.session, "get", get)
    try:
        await provider.scrape("https://example.com")
        assert get.call_args.kwargs["verify"] is False
        admin_service.update_config({"verify_ssl": True})
        get.side_effect = requests.exceptions.SSLError("Synthetic invalid certificate")
        with pytest.raises(requests.exceptions.SSLError):
            await provider.scrape("https://example.com")
        assert get.call_count == 2
        assert get.call_args.kwargs["verify"] is True
    finally:
        provider.session.close()
