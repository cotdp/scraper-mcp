"""Perplexity AI service for web-grounded search and reasoning."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from scraper_mcp.admin.service import get_config
from scraper_mcp.metrics import record_request
from scraper_mcp.models.perplexity import (
    DEFAULT_ENABLED_PERPLEXITY_MODELS,
    PerplexityResponse,
)

# Perplexity SDK is optional - only import if available
try:
    from perplexity import APIStatusError, BadRequestError, Perplexity, RateLimitError

    PERPLEXITY_AVAILABLE = True
except ImportError:
    PERPLEXITY_AVAILABLE = False
    Perplexity = None  # type: ignore[misc, assignment]
    BadRequestError = Exception  # type: ignore[misc, assignment]
    RateLimitError = Exception  # type: ignore[misc, assignment]
    APIStatusError = Exception  # type: ignore[misc, assignment]


def _extract_prompt(messages: list[dict[str, str]], max_length: int = 80) -> str:
    """Extract user prompt from messages for logging (truncated for URL display).

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        max_length: Maximum length before truncation

    Returns:
        Truncated prompt string suitable for display
    """
    # Find the last user message
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            # Clean up whitespace
            content = " ".join(content.split())
            # Truncate if needed
            if len(content) > max_length:
                return content[: max_length - 3] + "..."
            return content
    return "(no prompt)"


def _extract_full_prompt(messages: list[dict[str, str]]) -> str:
    """Extract full untruncated user prompt from messages.

    Args:
        messages: List of message dicts with 'role' and 'content' keys

    Returns:
        Full prompt string (not truncated)
    """
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""


class PerplexityService:
    """Service for interacting with Perplexity AI API.

    This service provides methods for chat completions and reasoning tasks
    using Perplexity's web-grounded AI models.

    Settings are sourced from runtime config (overridable at runtime via the
    /api/config endpoint), which is itself seeded from environment variables:
    - PERPLEXITY_API_KEY: API key (tools disabled if missing). Runtime-overridable.
    - PERPLEXITY_ENABLED_MODELS: Comma-separated allowlist (default: sonar).
      Runtime-overridable. Models not on the list are rejected (opt-in).
    - PERPLEXITY_MODEL: Default model for the chat tool (default: sonar)
    - PERPLEXITY_REASONING_MODEL: Model for the reason tool (default: sonar-reasoning-pro)
    - PERPLEXITY_TEMPERATURE: Default temperature (default: 0.3)
    - PERPLEXITY_MAX_TOKENS: Default max tokens (default: 4000)
    """

    def __init__(self) -> None:
        """Initialize the Perplexity service with configuration from environment."""
        self.default_model = os.getenv("PERPLEXITY_MODEL", "sonar")
        self.default_temperature = float(os.getenv("PERPLEXITY_TEMPERATURE", "0.3"))
        self.default_max_tokens = int(os.getenv("PERPLEXITY_MAX_TOKENS", "4000"))
        self.reasoning_model = os.getenv("PERPLEXITY_REASONING_MODEL", "sonar-reasoning-pro")

        # Client is built lazily and rebuilt when the API key changes at runtime.
        self._client: Any = None
        self._client_key: str | None = None

    @property
    def api_key(self) -> str:
        """Current API key, preferring the runtime override then the environment."""
        return str(
            get_config("perplexity_api_key", "") or os.getenv("PERPLEXITY_API_KEY", "") or ""
        )

    @property
    def enabled_models(self) -> list[str]:
        """Models the user has opted into. Defaults to the cheap `sonar` model only."""
        models = get_config("perplexity_enabled_models", None)
        if not models:
            return list(DEFAULT_ENABLED_PERPLEXITY_MODELS)
        return list(models)

    def _get_client(self) -> Any:
        """Return a Perplexity client, (re)building it when the API key changes.

        Returns None when no API key is configured or the SDK is unavailable.
        """
        key = self.api_key
        if not key or not PERPLEXITY_AVAILABLE:
            self._client = None
            self._client_key = None
            return None
        if self._client is None or self._client_key != key:
            self._client = Perplexity(api_key=key)
            self._client_key = key
        return self._client

    @classmethod
    def is_available(cls) -> bool:
        """Check if Perplexity service is available.

        Used as the startup gate for registering the Perplexity tools, so it
        checks the environment directly. Returns True if the perplexity SDK is
        installed and PERPLEXITY_API_KEY is set. The API key can still be
        overridden at runtime via /api/config once the tools are registered.
        """
        return bool(os.getenv("PERPLEXITY_API_KEY")) and PERPLEXITY_AVAILABLE

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> PerplexityResponse:
        """Send a chat completion request to Perplexity.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            model: Model to use (default: from PERPLEXITY_MODEL env var)
            temperature: Response creativity 0-2 (default: from env var)
            max_tokens: Maximum response tokens (default: from env var)

        Returns:
            PerplexityResponse with content, citations, and usage stats
        """
        client = self._get_client()
        if not client:
            prompt = _extract_prompt(messages)
            record_request(
                url=f'perplexity://{model or self.default_model}  "{prompt}"',
                success=False,
                status_code=503,
                elapsed_ms=0,
                attempts=1,
                error="Perplexity service not available",
                request_type="perplexity",
            )
            return self._error_response(
                "Perplexity service not available", model or self.default_model
            )

        # Apply defaults
        model = model or self.default_model
        temperature = temperature if temperature is not None else self.default_temperature
        max_tokens = max_tokens if max_tokens is not None else self.default_max_tokens

        # Extract prompt for metrics logging
        prompt = _extract_prompt(messages)
        metrics_url = f'perplexity://{model}  "{prompt}"'

        # Enforce the enabled-models allowlist (opt-in). Models not enabled are
        # rejected before any (billable) API call is made.
        enabled = self.enabled_models
        if model not in enabled:
            record_request(
                url=metrics_url,
                success=False,
                status_code=403,
                elapsed_ms=0,
                attempts=1,
                error=f"Model '{model}' is not enabled",
                request_type="perplexity",
            )
            return self._error_response(
                f"Model '{model}' is not enabled. Enabled models: {enabled}. "
                f"Enable it via the 'perplexity_enabled_models' setting (opt-in) "
                f"to control cost.",
                model,
            )

        start_time = time.time()

        try:
            # Run synchronous SDK call in executor to avoid blocking
            loop = asyncio.get_event_loop()
            completion = await loop.run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
            )

            elapsed_ms = int((time.time() - start_time) * 1000)

            # Extract response data
            choice = completion.choices[0] if completion.choices else None
            raw_content = choice.message.content if choice and choice.message else ""
            # Ensure content is a string (SDK may return structured content)
            content = str(raw_content) if raw_content else ""

            # Extract citations if available
            citations: list[str] = []
            if hasattr(completion, "citations") and completion.citations:
                citations = list(completion.citations)

            # Extract usage stats
            usage: dict[str, int] = {}
            if hasattr(completion, "usage") and completion.usage:
                usage = {
                    "prompt_tokens": completion.usage.prompt_tokens or 0,
                    "completion_tokens": completion.usage.completion_tokens or 0,
                    "total_tokens": completion.usage.total_tokens or 0,
                }

            # Record successful request in metrics with full response data
            record_request(
                url=metrics_url,
                success=True,
                status_code=200,
                elapsed_ms=elapsed_ms,
                attempts=1,
                request_type="perplexity",
                perplexity_data={
                    "model": model,
                    "full_prompt": _extract_full_prompt(messages),
                    "content": content,
                    "citations": citations,
                    "usage": usage,
                },
            )

            return PerplexityResponse(
                content=content or "",
                model=model,
                citations=citations,
                usage=usage,
                metadata={
                    "request_id": getattr(completion, "id", None),
                    "elapsed_ms": elapsed_ms,
                },
            )

        except RateLimitError as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            record_request(
                url=metrics_url,
                success=False,
                status_code=429,
                elapsed_ms=elapsed_ms,
                attempts=1,
                error=f"Rate limit exceeded: {e}",
                request_type="perplexity",
            )
            return self._error_response(
                f"Rate limit exceeded: {e}",
                model,
                rate_limited=True,
            )
        except BadRequestError as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            record_request(
                url=metrics_url,
                success=False,
                status_code=400,
                elapsed_ms=elapsed_ms,
                attempts=1,
                error=f"Bad request: {e}",
                request_type="perplexity",
            )
            return self._error_response(f"Bad request: {e}", model)
        except APIStatusError as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            record_request(
                url=metrics_url,
                success=False,
                status_code=500,
                elapsed_ms=elapsed_ms,
                attempts=1,
                error=f"API error: {e}",
                request_type="perplexity",
            )
            return self._error_response(f"API error: {e}", model)
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            record_request(
                url=metrics_url,
                success=False,
                status_code=500,
                elapsed_ms=elapsed_ms,
                attempts=1,
                error=f"Unexpected error: {type(e).__name__}: {e}",
                request_type="perplexity",
            )
            return self._error_response(f"Unexpected error: {type(e).__name__}: {e}", model)

    async def reason(
        self,
        query: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> PerplexityResponse:
        """Send a reasoning request to Perplexity using the reasoning model.

        Args:
            query: The question or problem to reason about
            temperature: Response creativity 0-2 (default: from env var)
            max_tokens: Maximum response tokens (default: from env var)

        Returns:
            PerplexityResponse with reasoned content, citations, and usage stats
        """
        # Convert single query to messages format
        messages = [{"role": "user", "content": query}]

        # Use reasoning model
        return await self.chat(
            messages=messages,
            model=self.reasoning_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _error_response(
        self,
        error_message: str,
        model: str,
        rate_limited: bool = False,
    ) -> PerplexityResponse:
        """Create an error response.

        Args:
            error_message: Description of the error
            model: Model that was requested
            rate_limited: Whether this was a rate limit error

        Returns:
            PerplexityResponse with error details in metadata
        """
        metadata: dict[str, Any] = {
            "error": error_message,
        }
        if rate_limited:
            metadata["rate_limited"] = True

        return PerplexityResponse(
            content="",
            model=model,
            citations=[],
            usage={},
            metadata=metadata,
        )


# Module-level singleton instance
_service: PerplexityService | None = None


def get_perplexity_service() -> PerplexityService:
    """Get or create the Perplexity service singleton.

    Returns:
        PerplexityService instance
    """
    global _service
    if _service is None:
        _service = PerplexityService()
    return _service
