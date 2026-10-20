"""Admin API routes for stats, config, and cache management."""

import json
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse

from scraper_mcp.admin.security import require_admin
from scraper_mcp.admin.service import (
    clear_cache,
    get_current_config,
    get_stats,
    update_config,
)
from scraper_mcp.cache_manager import get_cache_manager
from scraper_mcp.metrics import get_request_by_id
from scraper_mcp.providers.base import ScrapeResult

logger = logging.getLogger(__name__)


async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for container orchestration.

    Returns:
        JSONResponse with status: healthy
    """
    return JSONResponse({"status": "healthy"})


@require_admin
async def api_stats(request: Request) -> JSONResponse:
    """Get server statistics and metrics as JSON.

    Returns:
        JSONResponse with server stats including cache and request metrics
    """
    stats = get_stats()
    return JSONResponse(stats)


@require_admin
async def api_cache_clear(request: Request) -> JSONResponse:
    """Clear all cache entries.

    Returns:
        JSONResponse with operation status
    """
    try:
        result = clear_cache()
        return JSONResponse(result)
    except Exception:
        logger.error("Admin cache clear failed")
        return JSONResponse(
            {"status": "error", "message": "Cache could not be cleared"}, status_code=500
        )


@require_admin
async def api_config_get(request: Request) -> JSONResponse:
    """Get current runtime configuration.

    Returns:
        JSONResponse with current config values
    """
    config = get_current_config()
    return JSONResponse(config)


@require_admin
async def api_config_update(request: Request) -> JSONResponse:
    """Update runtime configuration.

    Returns:
        JSONResponse with operation status
    """
    try:
        raw_body = bytearray()
        async for chunk in request.stream():
            if len(raw_body) + len(chunk) > 65536:
                return JSONResponse(
                    {"status": "error", "message": "Configuration body is too large"},
                    status_code=413,
                )
            raw_body.extend(chunk)
        body = json.loads(raw_body)
        if not isinstance(body, dict) or not isinstance(body.get("config"), dict):
            return JSONResponse(
                {"status": "error", "message": "Expected a config object"}, status_code=400
            )
        config_updates = body["config"]
        result = update_config(config_updates)
        return JSONResponse(result)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return JSONResponse(
            {"status": "error", "message": "Invalid configuration payload"}, status_code=400
        )


@require_admin
async def api_request_details(request: Request) -> JSONResponse:
    """Get detailed information about a specific request by ID.

    For Perplexity requests: returns inline perplexity_data
    (model, prompt, response, citations, usage).
    For Scraper requests: looks up cached content by cache_key.

    Args:
        request: HTTP request with request_id path parameter

    Returns:
        JSONResponse with request details or error
    """
    request_id = request.path_params.get("request_id", "")

    if not request_id:
        return JSONResponse(
            {"status": "error", "message": "Request ID is required"}, status_code=400
        )

    # Find the request in metrics
    metrics = get_request_by_id(request_id)
    if not metrics:
        return JSONResponse({"status": "error", "message": "Request not found"}, status_code=404)

    # Build base response
    response = {
        "request_id": metrics.request_id,
        "request_type": metrics.request_type,
        "url": metrics.url,
        "timestamp": metrics.timestamp.isoformat(),
        "success": metrics.success,
        "status_code": metrics.status_code,
        "elapsed_ms": metrics.elapsed_ms,
        "attempts": metrics.attempts,
        "error": metrics.error,
    }

    # Add type-specific details
    if metrics.request_type == "perplexity":
        # Perplexity requests have inline data
        if metrics.perplexity_data:
            response["perplexity"] = metrics.perplexity_data
        else:
            response["perplexity"] = None
            response["details_unavailable"] = "Perplexity response data not captured"
    else:
        # Scraper requests - lookup from cache
        response["cache_key"] = metrics.cache_key
        if metrics.cache_key:
            cache = get_cache_manager()
            cached_data = cache.get(metrics.cache_key)
            if cached_data:
                # Extract content from ScrapeResult if needed
                if isinstance(cached_data, ScrapeResult):
                    content = cached_data.content
                    response["scrape_result"] = {
                        "url": cached_data.url,
                        "status_code": cached_data.status_code,
                        "content_type": cached_data.content_type,
                    }
                else:
                    content = cached_data

                # Return content preview (first 5000 chars)
                content_preview = content
                if isinstance(content, str) and len(content) > 5000:
                    content_preview = content[:5000]
                    response["content_truncated"] = True
                    response["full_content_length"] = len(content)
                response["cached_content"] = content_preview
            else:
                response["cached_content"] = None
                response["cache_expired"] = True
                response["details_unavailable"] = "Content no longer cached"
        else:
            response["cached_content"] = None
            response["details_unavailable"] = "Cache key not available"

    return JSONResponse(response)
