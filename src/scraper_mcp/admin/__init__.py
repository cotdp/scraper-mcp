"""Admin API functionality for configuration and monitoring.

This module provides administrative endpoints for:
- Health checks and server status
- Runtime configuration management
- Cache management operations
- Statistics and metrics gathering

The admin module follows a router -> service pattern:
- router.py: HTTP endpoint handlers
- service.py: Business logic for config, stats, and cache operations
"""

from scraper_mcp.admin.router import (
    api_cache_clear,
    api_config_get,
    api_config_update,
    api_stats,
    health_check,
)
from scraper_mcp.admin.service import (
    DEFAULT_CONCURRENCY,
    clear_cache,
    get_config,
    get_current_config,
    get_stats,
    update_config,
)

__all__ = [
    # Router functions
    "api_cache_clear",
    "api_config_get",
    "api_config_update",
    "api_stats",
    "health_check",
    # Service functions
    "clear_cache",
    "get_config",
    "get_current_config",
    "get_stats",
    "update_config",
    "DEFAULT_CONCURRENCY",
]
