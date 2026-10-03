"""Tests for admin runtime configuration, including Perplexity settings."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from scraper_mcp.admin import service as admin_service
from scraper_mcp.admin.service import (
    _mask_api_key,
    _parse_enabled_models,
    _parse_provider,
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


class TestParseProvider:
    """Tests for _parse_provider."""

    def test_none_returns_default(self) -> None:
        assert _parse_provider(None) == "auto"

    def test_empty_returns_default(self) -> None:
        assert _parse_provider("") == "auto"

    def test_valid_providers(self) -> None:
        assert _parse_provider("perplexity") == "perplexity"
        assert _parse_provider("openrouter") == "openrouter"
        assert _parse_provider("auto") == "auto"

    def test_case_and_whitespace_normalized(self) -> None:
        assert _parse_provider(" OpenRouter ") == "openrouter"

    def test_unknown_falls_back_to_default(self) -> None:
        assert _parse_provider("gemini") == "auto"


class TestUpdateConfigOpenRouter:
    """Tests for the OpenRouter backend settings via update_config."""

    def test_update_openrouter_key_stored_plaintext_but_masked_in_output(self) -> None:
        result = update_config({"openrouter_api_key": "sk-or-secret-1234567890"})

        assert "openrouter_api_key" in result["updated"]
        assert get_config("openrouter_api_key") == "sk-or-secret-1234567890"
        assert result["current_config"]["openrouter_api_key"] == "sk-o...7890"

    def test_update_provider(self) -> None:
        result = update_config({"perplexity_provider": "openrouter"})
        assert "perplexity_provider" in result["updated"]
        assert get_config("perplexity_provider") == "openrouter"

    def test_provider_normalized(self) -> None:
        update_config({"perplexity_provider": " Perplexity "})
        assert get_config("perplexity_provider") == "perplexity"

    def test_unknown_provider_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown Perplexity provider"):
            update_config({"perplexity_provider": "gemini"})

    def test_providers_advertised_in_current_config(self) -> None:
        current = get_current_config()
        assert current["available_perplexity_providers"] == ["auto", "perplexity", "openrouter"]
