"""Admin API routes for stats, config, and cache management."""

from starlette.requests import Request
from starlette.responses import JSONResponse

from scraper_mcp.admin.service import (
    clear_cache,
    get_current_config,
    get_stats,
    update_config,
)


async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for container orchestration.

    Returns:
        JSONResponse with status: healthy
    """
    return JSONResponse({"status": "healthy"})


async def api_stats(request: Request) -> JSONResponse:
    """Get server statistics and metrics as JSON.

    Returns:
        JSONResponse with server stats including cache and request metrics
    """
    stats = get_stats()
    return JSONResponse(stats)


async def api_cache_clear(request: Request) -> JSONResponse:
    """Clear all cache entries.

    Returns:
        JSONResponse with operation status
    """
    try:
        result = clear_cache()
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse(
            {
                "status": "error",
                "message": str(e)
            },
            status_code=500
        )


async def api_config_get(request: Request) -> JSONResponse:
    """Get current runtime configuration.

    Returns:
        JSONResponse with current config values
    """
    config = get_current_config()
    return JSONResponse(config)


async def api_config_update(request: Request) -> JSONResponse:
    """Update runtime configuration.

    Returns:
        JSONResponse with operation status
    """
    try:
        body = await request.json()
        config_updates = body.get("config", {})
        result = update_config(config_updates)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse(
            {
                "status": "error",
                "message": str(e)
            },
            status_code=500
        )
