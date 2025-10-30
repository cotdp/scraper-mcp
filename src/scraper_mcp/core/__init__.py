"""Core infrastructure and shared utilities.

This module provides foundational components used across the application:
- Provider initialization and management
- Shared configuration and constants
- Common utilities and helpers

The core module is imported by other domain modules and provides the
single source of truth for provider instances and configuration.
"""

from scraper_mcp.core.providers import (
    default_provider,
    get_provider,
)

__all__ = [
    "default_provider",
    "get_provider",
]
