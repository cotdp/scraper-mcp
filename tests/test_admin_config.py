"""Tests for admin runtime configuration, including Perplexity settings."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

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


class TestSecretConfigRoundtrip:
    @pytest.mark.parametrize("key", ["http_proxy", "https_proxy"])
    def test_proxy_secret_never_leaves_config_and_roundtrips(self, key: str) -> None:
        secret = "http://username:password@proxy.example:8080/token?api_key=other-secret"
        updated = update_config({key: secret})
        public = get_current_config()["config"]
        assert public[key] == "[REDACTED]"
        assert secret not in str(updated)
        assert "username" not in str(public)
        assert "other-secret" not in str(public)

        # The dashboard posts its displayed values alongside unrelated changes.
        result = update_config({key: public[key], "default_timeout": 42})
        assert get_config(key) == secret
        assert key not in result["updated"]
        assert get_config("default_timeout") == 42

        update_config({"concurrency": 4})
        assert get_config(key) == secret
        update_config({key: ""})
        assert get_config(key) == ""
        assert get_current_config()["config"][key] == ""

    @pytest.mark.parametrize("key", ["perplexity_api_key", "openrouter_api_key"])
    def test_masked_api_key_roundtrip_preserves_value(self, key: str) -> None:
        secret = "example-secret-key-1234567890"
        update_config({key: secret})
        update_config({key: get_current_config()["config"][key]})
        assert get_config(key) == secret
        update_config({key: ""})
        assert get_config(key) == ""

    def test_validation_failure_does_not_partially_mutate_config(self) -> None:
        before = get_config("default_timeout")
        with pytest.raises(ValueError):
            update_config({"default_timeout": 99, "perplexity_provider": "invalid"})
        assert get_config("default_timeout") == before

    def test_redacted_placeholder_is_not_a_new_proxy(self) -> None:
        update_config({"http_proxy": ""})
        with pytest.raises(ValueError, match="masked proxy"):
            update_config({"http_proxy": "[REDACTED]"})
        assert get_config("http_proxy") == ""

    @pytest.mark.parametrize("key", ["perplexity_api_key", "openrouter_api_key"])
    @pytest.mark.parametrize("old_secret", ["short", "previous-api-key-1234567890"])
    def test_stale_mask_preserves_rotated_api_key(self, key: str, old_secret: str) -> None:
        update_config({key: old_secret})
        stale_mask = get_current_config()["config"][key]
        current_secret = "rotated-api-key-0987654321"
        update_config({key: current_secret})
        result = update_config({key: f" {stale_mask} "})
        assert get_config(key) == current_secret
        assert key not in result["updated"]

    @pytest.mark.parametrize("key", ["perplexity_api_key", "openrouter_api_key"])
    def test_mask_cannot_be_installed_as_new_api_key(self, key: str) -> None:
        update_config({key: ""})
        with pytest.raises(ValueError, match="masked proxy URL or API key"):
            update_config({key: "***"})
        assert get_config(key) == ""

    @pytest.mark.parametrize("invalid_value", [False, None, 0, []])
    def test_false_values_do_not_clear_secrets_or_provider(self, invalid_value: Any) -> None:
        keys = ("http_proxy", "https_proxy", "perplexity_api_key", "openrouter_api_key")
        update_config(dict.fromkeys(keys, "configured-secret-1234567890"))
        before = dict(admin_service._runtime_config)
        result = update_config(dict.fromkeys((*keys, "perplexity_provider"), invalid_value))
        assert result["updated"] == []
        assert admin_service._runtime_config == before


@pytest.mark.parametrize("invalid_value", [True, False])
def test_boolean_values_do_not_replace_numeric_settings(invalid_value: bool) -> None:
    keys = (
        "concurrency",
        "default_timeout",
        "default_max_retries",
        "cache_ttl_default",
        "cache_ttl_static",
        "cache_ttl_realtime",
    )
    before = {key: get_config(key) for key in keys}
    result = update_config(dict.fromkeys(keys, invalid_value))
    assert result["updated"] == []
    assert {key: get_config(key) for key in keys} == before
