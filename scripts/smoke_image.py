"""Exercise a built production image offline, including HTTP MCP and Chromium.

Run with:
    docker run --rm --network none -i IMAGE python - < scripts/smoke_image.py
"""

from __future__ import annotations

import asyncio
import json
import os
from importlib.metadata import version


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


async def main() -> None:
    """Run isolated, synthetic checks and shut the temporary server down cleanly."""
    require(os.getuid() != 0, "The production image must run as a non-root user")
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
        "PERPLEXITY_API_KEY",
        "SCRAPEOPS_API_KEY",
        "SCRAPER_ADMIN_ALLOWED_ORIGINS",
    ):
        os.environ.pop(name, None)
    token = "synthetic-container-smoke"  # noqa: S105
    os.environ["SCRAPER_ADMIN_TOKEN"] = token
    os.environ["OPENROUTER_API_KEY"] = "synthetic-openrouter-smoke"

    import httpx
    import perplexity
    import uvicorn
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from starlette.requests import Request
    from starlette.responses import HTMLResponse

    from scraper_mcp.cache_manager import get_cache_manager
    from scraper_mcp.providers.playwright_provider import shutdown_browser_pool
    from scraper_mcp.server import mcp

    require(callable(perplexity.Perplexity), "The direct Perplexity SDK is missing")

    async def fixture(request: Request) -> HTMLResponse:
        return HTMLResponse(
            '<html><body><h1 id="result">Static fixture</h1>'
            '<script>document.querySelector("#result").textContent = '
            '"Rendered by Chromium";</script></body></html>'
        )

    mcp.custom_route("/smoke-fixture", methods=["GET"])(fixture)

    server = uvicorn.Server(
        uvicorn.Config(
            mcp.streamable_http_app(),
            host="127.0.0.1",
            port=8000,
            log_level="warning",
            proxy_headers=False,
        )
    )
    server_task = asyncio.create_task(server.serve())
    try:
        async with asyncio.timeout(90):
            while not server.started:
                if server_task.done():
                    await server_task
                    raise RuntimeError("The smoke-test HTTP server exited before startup")
                await asyncio.sleep(0.05)
            async with httpx.AsyncClient(
                base_url="http://127.0.0.1:8000", trust_env=False, timeout=30
            ) as client:
                health = await client.get("/healthz")
                health.raise_for_status()
                require(health.json() == {"status": "healthy"}, "Health response changed")
                denied = await client.get("/api/config")
                require(denied.status_code == 401, "Unauthenticated administration was allowed")
                os.environ.pop("SCRAPER_ADMIN_TOKEN")
                disabled = await client.get("/api/config")
                require(disabled.status_code == 503, "Unconfigured administration was allowed")
                os.environ["SCRAPER_ADMIN_TOKEN"] = token
                headers = {"Authorization": f"Bearer {token}"}
                config = await client.get("/api/config", headers=headers)
                config.raise_for_status()
                require(config.json()["config"]["verify_ssl"] is True, "TLS defaults are unsafe")
                dashboard = await client.get("/", auth=("admin", token))
                dashboard.raise_for_status()
                require("Scraper" in dashboard.text, "Dashboard was not packaged")
                changed = await client.post(
                    "/api/config",
                    headers=headers,
                    json={"config": {"http_proxy": "http://fictional:user@proxy.invalid:8080"}},
                )
                changed.raise_for_status()
                require("fictional" not in changed.text, "Proxy credentials escaped config")

                async with (
                    streamable_http_client("http://127.0.0.1:8000/mcp", http_client=client) as (
                        read,
                        write,
                        _,
                    ),
                    ClientSession(read, write) as session,
                ):
                    await session.initialize()
                    names = {tool.name for tool in (await session.list_tools()).tools}
                    require(
                        {"scrape_url", "scrape_url_text", "perplexity", "perplexity_reason"}
                        <= names,
                        "Production tools or OpenRouter-only registration are missing",
                    )
                    for render_js, expected in (
                        (False, "Static fixture"),
                        (True, "Rendered by Chromium"),
                    ):
                        result = await session.call_tool(
                            "scrape_url_text",
                            {
                                "urls": ["http://127.0.0.1:8000/smoke-fixture"],
                                "render_js": render_js,
                                "max_retries": 0,
                                "css_selector": "#result",
                            },
                        )
                        require(not result.isError, "MCP scrape tool returned a protocol error")
                        require(
                            expected in result.model_dump_json(),
                            f"Packaged scraper did not return {expected}",
                        )
                require(
                    int(get_cache_manager().get_stats()["entry_count"]) >= 1,
                    "Production cache did not persist scrape results",
                )
        print(
            json.dumps(
                {
                    "version": version("scraper-mcp"),
                    "non_root": True,
                    "health": True,
                    "admin_authentication": True,
                    "tls_verification_default": True,
                    "openrouter_tool_registration": True,
                    "mcp_http_roundtrip": True,
                    "static_scraping": True,
                    "chromium_rendering": True,
                    "persistent_cache": True,
                }
            )
        )
    finally:
        await shutdown_browser_pool()
        server.should_exit = True
        await server_task
        get_cache_manager().close()


if __name__ == "__main__":
    asyncio.run(main())
