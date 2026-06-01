"""Tests for admin runtime configuration, including Perplexity settings."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from scraper_mcp.admin import service as admin_service
from scraper_mcp.admin.service import (
    _mask_api_key,
    _parse_enabled_models,
    get_config,
    get_current_config,
    update_config,
)


@pytest.fixture(autouse=True)
def _restore_runtime_config() -> Iterator[None]:
    """Snapshot and restore the global runtime config around each test."""
    snapshot = dict(admin_service._runtime_config)
    yield
    admin_service._runtime_config.clear()
    admin_service._runtime_config.update(snapshot)


class TestMaskApiKey:
    """Tests for _mask_api_key."""

    def test_empty(self) -> None:
        assert _mask_api_key("") == ""

    def test_short_key_fully_masked(self) -> None:
        assert _mask_api_key("abc123") == "***"

    def test_long_key_shows_prefix_and_suffix(self) -> None:
        masked = _mask_api_key("pplx-1234567890abcdef")
        assert masked == "pplx...cdef"
        assert "567890" not in masked


class TestParseEnabledModels:
    """Tests for _parse_enabled_models."""

    def test_none_returns_default(self) -> None:
        assert _parse_enabled_models(None) == ["sonar"]

    def test_empty_returns_default(self) -> None:
        assert _parse_enabled_models("") == ["sonar"]

    def test_parses_comma_separated(self) -> None:
        assert _parse_enabled_models("sonar, sonar-pro") == ["sonar", "sonar-pro"]

    def test_ignores_unknown_models(self) -> None:
        assert _parse_enabled_models("sonar,not-a-model") == ["sonar"]

    def test_all_unknown_falls_back_to_default(self) -> None:
        assert _parse_enabled_models("bogus,nope") == ["sonar"]


class TestUpdateConfigPerplexity:
    """Tests for updating Perplexity settings via update_config."""

    def test_update_api_key_stored_plaintext_but_masked_in_output(self) -> None:
        result = update_config({"perplexity_api_key": "pplx-secret-1234567890"})

        assert "perplexity_api_key" in result["updated"]
        # Stored value is the real key for the service to use
        assert get_config("perplexity_api_key") == "pplx-secret-1234567890"
        # But the returned/displayed value is masked
        assert result["current_config"]["perplexity_api_key"] == "pplx...7890"

    def test_get_current_config_masks_api_key(self) -> None:
        update_config({"perplexity_api_key": "pplx-secret-1234567890"})
        current = get_current_config()
        assert current["config"]["perplexity_api_key"] == "pplx...7890"
        assert "available_perplexity_models" in current

    def test_enable_models_opt_in(self) -> None:
        result = update_config({"perplexity_enabled_models": ["sonar", "sonar-reasoning-pro"]})
        assert "perplexity_enabled_models" in result["updated"]
        assert get_config("perplexity_enabled_models") == ["sonar", "sonar-reasoning-pro"]

    def test_unknown_model_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown Perplexity model"):
            update_config({"perplexity_enabled_models": ["sonar", "gpt-4"]})

    def test_non_list_enabled_models_ignored(self) -> None:
        result = update_config({"perplexity_enabled_models": "sonar"})
        assert "perplexity_enabled_models" not in result["updated"]
