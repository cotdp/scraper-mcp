"""Admin service layer for configuration and stats management."""

from __future__ import annotations

import logging
import os
from typing import Any

from scraper_mcp.cache import clear_all_cache, get_cache_stats
from scraper_mcp.metrics import get_metrics
from scraper_mcp.models.perplexity import (
    DEFAULT_ENABLED_PERPLEXITY_MODELS,
    PERPLEXITY_MODELS,
)

logger = logging.getLogger(__name__)

# Default concurrency limit for batch operations
DEFAULT_CONCURRENCY = 8


def _parse_enabled_models(raw: str | None) -> list[str]:
    """Parse a comma-separated PERPLEXITY_ENABLED_MODELS env value.

    Unknown model names are ignored. Falls back to the default allowlist when
    the value is empty or yields no valid models.

    Args:
        raw: Comma-separated model names (e.g. "sonar,sonar-pro")

    Returns:
        Ordered list of valid, enabled model names
    """
    if not raw:
        return list(DEFAULT_ENABLED_PERPLEXITY_MODELS)
    models = [m.strip() for m in raw.split(",") if m.strip() in PERPLEXITY_MODELS]
    return models or list(DEFAULT_ENABLED_PERPLEXITY_MODELS)


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
    # Perplexity settings (overridable at runtime via /api/config)
    "perplexity_api_key": os.getenv("PERPLEXITY_API_KEY", ""),
    "perplexity_enabled_models": _parse_enabled_models(os.getenv("PERPLEXITY_ENABLED_MODELS")),
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


def _mask_api_key(value: str) -> str:
    """Mask an API key for safe display, preserving a recognizable prefix/suffix.

    Args:
        value: The raw API key (may be empty)

    Returns:
        Masked representation that never reveals the full secret
    """
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _public_config() -> dict[str, Any]:
    """Return a copy of the runtime config with secrets masked for display."""
    public = dict(_runtime_config)
    public["perplexity_api_key"] = _mask_api_key(_runtime_config.get("perplexity_api_key", ""))
    return public


def get_stats() -> dict[str, Any]:
    """Get server statistics and metrics.

    Returns:
        Dictionary with server stats including cache and request metrics
    """
    metrics = get_metrics()
    stats = metrics.to_dict()

    # Add cache stats if available
    # Potential failures: cache manager initialization (OSError, PermissionError),
    # cache operations (RuntimeError from diskcache), or missing attributes
    try:
        stats["cache"] = get_cache_stats()
    except (OSError, PermissionError, RuntimeError, AttributeError) as e:
        logger.debug(f"Cache stats unavailable: {e}")
        stats["cache"] = {"error": "Cache stats unavailable"}

    return stats


def get_current_config() -> dict[str, Any]:
    """Get current runtime configuration.

    Returns:
        Dictionary with current config, defaults, and note
    """
    return {
        "config": _public_config(),
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
            "perplexity_api_key": "",
            "perplexity_enabled_models": list(DEFAULT_ENABLED_PERPLEXITY_MODELS),
        },
        "available_perplexity_models": list(PERPLEXITY_MODELS),
        "note": "Changes are not persisted and will reset on server restart",
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
        "perplexity_api_key",
        "perplexity_enabled_models",
    }

    updated = []
    for key, value in config_updates.items():
        if key in valid_keys:
            # Basic type validation
            if key == "concurrency" and isinstance(value, int) and 1 <= value <= 50:
                _runtime_config[key] = value
                updated.append(key)
            elif (
                key in ("default_timeout", "default_max_retries")
                and isinstance(value, int)
                and value > 0
            ):
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
            elif key == "perplexity_api_key" and isinstance(value, str):
                _runtime_config[key] = value.strip()
                updated.append(key)
            elif key == "perplexity_enabled_models" and isinstance(value, list):
                # Only accept known model names; reject unknown values to surface typos
                cleaned = [m for m in value if isinstance(m, str) and m in PERPLEXITY_MODELS]
                if len(cleaned) == len(value):
                    _runtime_config[key] = cleaned
                    updated.append(key)
                else:
                    invalid = [m for m in value if m not in PERPLEXITY_MODELS]
                    raise ValueError(
                        f"Unknown Perplexity model(s): {invalid}. "
                        f"Valid models: {list(PERPLEXITY_MODELS)}"
                    )

    return {
        "status": "success",
        "message": f"Updated {len(updated)} config value(s)",
        "updated": updated,
        "current_config": _public_config(),
    }


def clear_cache() -> dict[str, str]:
    """Clear all cache entries.

    Returns:
        Dictionary with status and message
    """
    clear_all_cache()
    return {"status": "success", "message": "Cache cleared successfully"}
