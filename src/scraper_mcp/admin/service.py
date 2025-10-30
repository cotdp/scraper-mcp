"""Admin service layer for configuration and stats management."""

from __future__ import annotations

import os
from typing import Any

from scraper_mcp.cache import clear_all_cache, get_cache_stats
from scraper_mcp.metrics import get_metrics

# Default concurrency limit for batch operations
DEFAULT_CONCURRENCY = 8

# Runtime configuration overrides (not persisted)
_runtime_config: dict[str, Any] = {
    "concurrency": DEFAULT_CONCURRENCY,
    "default_timeout": 30,
    "default_max_retries": 3,
    "cache_ttl_default": 3600,
    "cache_ttl_static": 86400,
    "cache_ttl_realtime": 300,
    "proxy_enabled": False,
    "http_proxy": "",
    "https_proxy": "",
    "no_proxy": "",
    "verify_ssl": False,  # SSL certificate verification (disabled by default)
}

# Initialize proxy settings from environment variables if present
_http_proxy_env = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
_https_proxy_env = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
_no_proxy_env = os.getenv("NO_PROXY") or os.getenv("no_proxy")

if _http_proxy_env or _https_proxy_env:
    _runtime_config["proxy_enabled"] = True
    if _http_proxy_env:
        _runtime_config["http_proxy"] = _http_proxy_env
    if _https_proxy_env:
        _runtime_config["https_proxy"] = _https_proxy_env
    if _no_proxy_env:
        _runtime_config["no_proxy"] = _no_proxy_env

    # Log proxy initialization
    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        f"Proxy enabled from environment variables: "
        f"HTTP_PROXY={_http_proxy_env}, HTTPS_PROXY={_https_proxy_env}, NO_PROXY={_no_proxy_env}"
    )


def get_config(key: str, default: Any = None) -> Any:
    """Get a configuration value with runtime override support.

    Args:
        key: Configuration key
        default: Default value if key not found

    Returns:
        Configuration value or default
    """
    return _runtime_config.get(key, default)


def get_stats() -> dict[str, Any]:
    """Get server statistics and metrics.

    Returns:
        Dictionary with server stats including cache and request metrics
    """
    metrics = get_metrics()
    stats = metrics.to_dict()

    # Add cache stats if available
    try:
        stats["cache"] = get_cache_stats()
    except Exception:
        stats["cache"] = {"error": "Cache stats unavailable"}

    return stats


def get_current_config() -> dict[str, Any]:
    """Get current runtime configuration.

    Returns:
        Dictionary with current config, defaults, and note
    """
    return {
        "config": _runtime_config,
        "defaults": {
            "concurrency": DEFAULT_CONCURRENCY,
            "default_timeout": 30,
            "default_max_retries": 3,
            "cache_ttl_default": 3600,
            "cache_ttl_static": 86400,
            "cache_ttl_realtime": 300,
            "proxy_enabled": False,
            "http_proxy": "",
            "https_proxy": "",
            "no_proxy": "",
            "verify_ssl": False,
        },
        "note": "Changes are not persisted and will reset on server restart"
    }


def update_config(config_updates: dict[str, Any]) -> dict[str, Any]:
    """Update runtime configuration.

    Args:
        config_updates: Dictionary of config key-value pairs to update

    Returns:
        Dictionary with status, message, updated keys, and current config

    Raises:
        ValueError: If validation fails
    """
    valid_keys = {
        "concurrency",
        "default_timeout",
        "default_max_retries",
        "cache_ttl_default",
        "cache_ttl_static",
        "cache_ttl_realtime",
        "proxy_enabled",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "verify_ssl",
    }

    updated = []
    for key, value in config_updates.items():
        if key in valid_keys:
            # Basic type validation
            if key == "concurrency" and isinstance(value, int) and 1 <= value <= 50:
                _runtime_config[key] = value
                updated.append(key)
            elif key in ("default_timeout", "default_max_retries") and isinstance(value, int) and value > 0:
                _runtime_config[key] = value
                updated.append(key)
            elif key.startswith("cache_ttl_") and isinstance(value, int) and value >= 0:
                _runtime_config[key] = value
                updated.append(key)
            elif key in ("proxy_enabled", "verify_ssl") and isinstance(value, bool):
                _runtime_config[key] = value
                updated.append(key)
            elif key in ("http_proxy", "https_proxy", "no_proxy") and isinstance(value, str):
                _runtime_config[key] = value
                updated.append(key)

    return {
        "status": "success",
        "message": f"Updated {len(updated)} config value(s)",
        "updated": updated,
        "current_config": _runtime_config
    }


def clear_cache() -> dict[str, str]:
    """Clear all cache entries.

    Returns:
        Dictionary with status and message
    """
    clear_all_cache()
    return {
        "status": "success",
        "message": "Cache cleared successfully"
    }
