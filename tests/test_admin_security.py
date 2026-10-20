"""Integration regressions for every custom admin route on both HTTP transports."""

from __future__ import annotations

import base64
from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from scraper_mcp.admin import service as admin_service
from scraper_mcp.server import mcp


@pytest.fixture(autouse=True)
def restore_config(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("SCRAPER_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.delenv("SCRAPER_ADMIN_ALLOWED_ORIGINS", raising=False)
    snapshot = dict(admin_service._runtime_config)
    yield
    admin_service._runtime_config.clear()
    admin_service._runtime_config.update(snapshot)


@pytest.fixture(params=["streamable-http", "sse"])
def client(request: pytest.FixtureRequest) -> Iterator[TestClient]:
    app = mcp.streamable_http_app() if request.param == "streamable-http" else mcp.sse_app()
    # These custom routes do not use the MCP session manager. Do not restart
    # the singleton manager's lifespan for each request/transport.
    client = TestClient(app, base_url="http://localhost:8000", client=("127.0.0.1", 50000))
    client.headers["Authorization"] = "Bearer test-admin-token"
    yield client
    client.close()


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/"),
        ("GET", "/api/stats"),
        ("GET", "/api/config"),
        ("POST", "/api/config"),
        ("POST", "/api/cache/clear"),
        ("GET", "/api/requests/missing/details"),
    ],
)
def test_all_admin_routes_require_configured_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, method: str, path: str
) -> None:
    monkeypatch.setenv("SCRAPER_ADMIN_TOKEN", "test-admin-token")
    client.headers.pop("authorization")
    response = client.request(method, path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic ")
    assert response.headers["cache-control"] == "no-store"
    assert "test-admin-token" not in response.text


def test_health_is_public_with_admin_auth_enabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SCRAPER_ADMIN_TOKEN", "test-admin-token")
    client.headers.pop("authorization")
    assert client.get("/healthz").json() == {"status": "healthy"}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/"),
        ("GET", "/api/stats"),
        ("GET", "/api/config"),
        ("POST", "/api/config"),
        ("POST", "/api/cache/clear"),
        ("GET", "/api/requests/missing/details"),
    ],
)
def test_unconfigured_admin_is_disabled_even_on_loopback(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, method: str, path: str
) -> None:
    monkeypatch.delenv("SCRAPER_ADMIN_TOKEN")
    response = client.request(method, path)
    assert response.status_code == 503
    assert "SCRAPER_ADMIN_TOKEN" in response.json()["message"]
    assert client.get("/healthz").status_code == 200


def test_authenticated_admin_response_is_not_cached(client: TestClient) -> None:
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "http://localhost:9000"},
        {"Origin": "https://attacker.example"},
        {"Origin": "null"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_authenticated_browser_cannot_cross_origins(
    client: TestClient, headers: dict[str, str]
) -> None:
    assert client.get("/api/config", headers=headers).status_code == 403


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Forwarded-For": "127.0.0.1"},
        {"Forwarded": "for=127.0.0.1;host=localhost"},
        {"X-Forwarded-Host": "localhost"},
        {"X-Real-IP": "127.0.0.1"},
    ],
)
def test_forwarded_headers_do_not_grant_access(client: TestClient, headers: dict[str, str]) -> None:
    client.headers.pop("authorization")
    assert client.get("/api/config", headers=headers).status_code == 401


def test_remote_peer_with_local_host_is_denied() -> None:
    with TestClient(
        mcp.sse_app(), base_url="http://localhost:8000", client=("192.0.2.7", 50000)
    ) as remote:
        response = remote.get("/api/config")
    assert response.status_code == 401


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "Basic"])
def test_valid_auth_works_for_remote_clients(monkeypatch: pytest.MonkeyPatch, scheme: str) -> None:
    token = "test-admin-token"
    monkeypatch.setenv("SCRAPER_ADMIN_TOKEN", token)
    credential = (
        base64.b64encode(f"admin:{token}".encode()).decode() if scheme == "Basic" else token
    )
    with TestClient(
        mcp.sse_app(), base_url="https://scraper.example", client=("192.0.2.7", 50000)
    ) as remote:
        response = remote.get("/api/config", headers={"Authorization": f"{scheme} {credential}"})
    assert response.status_code == 200
    assert token not in response.text


@pytest.mark.parametrize(
    "authorization",
    [
        "Bearer wrong",
        "Bearer test-admin-token-extra",
        "Bearer test-admin-token ",
        "Bearer  test-admin-token",
        "NotBearer test-admin-token",
        "Basic !!!!",
        "Basic YWRtaW46d3Jvbmc=",
        "Basic dXNlcjp0ZXN0LWFkbWluLXRva2Vu",
    ],
)
def test_authorization_requires_exact_credential(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, authorization: str
) -> None:
    monkeypatch.setenv("SCRAPER_ADMIN_TOKEN", "test-admin-token")
    assert client.get("/api/config", headers={"Authorization": authorization}).status_code == 401


@pytest.mark.parametrize("header", ["authorization", "host", "origin"])
def test_duplicate_security_headers_are_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, header: str
) -> None:
    monkeypatch.setenv("SCRAPER_ADMIN_TOKEN", "test-admin-token")
    response = client.get("/api/config", headers=[(header, "first"), (header, "second")])
    assert response.status_code == 400


@pytest.mark.parametrize("host", ["[", "localhost:invalid", "admin@localhost", "*", "local host"])
def test_malformed_hosts_return_client_errors(client: TestClient, host: str) -> None:
    assert client.get("/api/config", headers={"Host": host}).status_code == 400


def test_authenticated_cross_origin_mutation_is_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SCRAPER_ADMIN_TOKEN", "test-admin-token")
    before = admin_service.get_config("default_timeout")
    response = client.post(
        "/api/config",
        auth=("admin", "test-admin-token"),
        headers={"Origin": "https://attacker.example"},
        json={"config": {"default_timeout": 99}},
    )
    assert response.status_code == 403
    assert admin_service.get_config("default_timeout") == before


def test_reverse_proxy_origin_requires_explicit_allowlist(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SCRAPER_ADMIN_TOKEN", "test-admin-token")
    headers = {
        "Authorization": "Bearer test-admin-token",
        "Origin": "https://scraper.example",
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "scraper.example",
    }
    assert client.get("/api/config", headers=headers).status_code == 403
    monkeypatch.setenv("SCRAPER_ADMIN_ALLOWED_ORIGINS", "https://scraper.example")
    assert client.get("/api/config", headers=headers).status_code == 200


@pytest.mark.parametrize("path", ["/api/config", "/api/cache/clear"])
def test_form_mutations_are_rejected(client: TestClient, path: str) -> None:
    response = client.post(path, data={"config": '{"verify_ssl":false}'})
    assert response.status_code == 415


@pytest.mark.parametrize("payload", ["[]", '{"config":[]}', "{}", "{not-json", "null"])
def test_invalid_config_payload_returns_client_error(client: TestClient, payload: str) -> None:
    response = client.post(
        "/api/config", content=payload, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400


def test_config_error_does_not_echo_secrets(client: TestClient) -> None:
    response = client.post(
        "/api/config", json={"config": {"perplexity_provider": "accidentally-pasted-secret"}}
    )
    assert response.status_code == 400
    assert "accidentally-pasted-secret" not in response.text


def test_config_body_limit(client: TestClient) -> None:
    before = admin_service.get_config("default_timeout")
    response = client.post(
        "/api/config", json={"config": {"default_timeout": 42, "http_proxy": "x" * 65536}}
    )
    assert response.status_code == 413
    assert admin_service.get_config("default_timeout") == before


def test_deeply_nested_config_returns_client_error(client: TestClient) -> None:
    payload = '{"config":{"ignored":' + "[" * 10000 + "0" + "]" * 10000 + "}}"
    response = client.post(
        "/api/config", content=payload, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400


def test_valid_json_config_mutation(client: TestClient) -> None:
    response = client.post(
        "/api/config",
        headers={"Origin": "http://localhost:8000"},
        json={"config": {"default_timeout": 42}},
    )
    assert response.status_code == 200
    assert admin_service.get_config("default_timeout") == 42


def test_dashboard_uses_browser_auth_without_storing_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SCRAPER_ADMIN_TOKEN", "test-admin-token")
    response = client.get("/", auth=("admin", "test-admin-token"))
    assert response.status_code == 200
    assert "test-admin-token" not in response.text
    assert "localStorage" not in response.text
    assert "sessionStorage" not in response.text
    assert response.headers["x-frame-options"] == "DENY"
