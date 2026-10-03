"""Perplexity AI service for web-grounded search and reasoning.

Supports two interchangeable backends serving the same Sonar models:

- **perplexity**: the official Perplexity API via the ``perplexityai`` SDK
- **openrouter**: OpenRouter's OpenAI-compatible API (models addressed as
  ``perplexity/<model>``), called directly over HTTPS with ``requests``

The backend is selected by the ``perplexity_provider`` runtime config key
(seeded from ``PERPLEXITY_PROVIDER``). The default ``auto`` prefers direct
Perplexity when its API key is configured, falling back to OpenRouter.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, TypedDict

import requests

from scraper_mcp.admin.service import get_config
from scraper_mcp.metrics import record_request
from scraper_mcp.models.perplexity import (
    DEFAULT_ENABLED_PERPLEXITY_MODELS,
    DEFAULT_PERPLEXITY_PROVIDER,
    OPENROUTER_MODEL_PREFIX,
    PERPLEXITY_PROVIDERS,
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

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_TIMEOUT_SECONDS = 120


class _CompletionResult(TypedDict):
    """Provider-neutral completion data returned by either backend."""

    content: str
    citations: list[str]
    usage: dict[str, int]
    request_id: str | None


class _CompletionError(Exception):
    """Normalized completion failure from either backend."""

    def __init__(self, message: str, status_code: int, rate_limited: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.rate_limited = rate_limited


def _elapsed_ms(start_time: float) -> int:
    """Return monotonic elapsed time in milliseconds."""
    return int((time.perf_counter() - start_time) * 1000)


def _http_status_code(value: object, default: int = 500) -> int:
    """Return a valid HTTP error status from an untrusted API payload."""
    if not isinstance(value, int | str):
        return default
    try:
        status_code = int(value)
    except ValueError:
        return default
    return status_code if 400 <= status_code <= 599 else default


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
    """Service for interacting with Perplexity Sonar models.

    This service provides methods for chat completions and reasoning tasks
    using Perplexity's web-grounded AI models, served either by the Perplexity
    API directly or by OpenRouter.

    Settings are sourced from runtime config (overridable at runtime via the
    /api/config endpoint), which is itself seeded from environment variables:
    - PERPLEXITY_API_KEY: Direct Perplexity API key. Runtime-overridable.
    - OPENROUTER_API_KEY: OpenRouter API key. Runtime-overridable.
    - PERPLEXITY_PROVIDER: Backend selection: auto | perplexity | openrouter
      (default: auto — direct Perplexity preferred, OpenRouter fallback).
      Runtime-overridable.
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
        """Direct Perplexity API key, preferring the runtime override then the environment."""
        return str(
            get_config("perplexity_api_key", "") or os.getenv("PERPLEXITY_API_KEY", "") or ""
        )

    @property
    def openrouter_api_key(self) -> str:
        """OpenRouter API key, preferring the runtime override then the environment."""
        return str(
            get_config("openrouter_api_key", "") or os.getenv("OPENROUTER_API_KEY", "") or ""
        )

    @property
    def provider(self) -> str:
        """Configured backend preference: auto, perplexity, or openrouter."""
        return str(
            get_config("perplexity_provider", "")
            or os.getenv("PERPLEXITY_PROVIDER", "")
            or DEFAULT_PERPLEXITY_PROVIDER
        )

    @property
    def enabled_models(self) -> list[str]:
        """Models the user has opted into. Defaults to the cheap `sonar` model only."""
        models = get_config("perplexity_enabled_models", None)
        if not models:
            return list(DEFAULT_ENABLED_PERPLEXITY_MODELS)
        return list(models)

    def _resolve_backend(self) -> str | None:
        """Resolve the effective backend for the next request.

        Returns "perplexity" or "openrouter", or None when no usable backend
        is configured. In "auto" mode direct Perplexity wins when its key is
        set (and the SDK is importable), otherwise OpenRouter is used.
        """
        provider = self.provider
        perplexity_ready = bool(self.api_key) and PERPLEXITY_AVAILABLE
        openrouter_ready = bool(self.openrouter_api_key)

        if provider == "perplexity":
            return "perplexity" if perplexity_ready else None
        if provider == "openrouter":
            return "openrouter" if openrouter_ready else None
        if provider != "auto":
            return None
        if perplexity_ready:
            return "perplexity"
        return "openrouter" if openrouter_ready else None

    def _get_client(self) -> Any:
        """Return a Perplexity SDK client, (re)building it when the API key changes.

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
        """Check if the Perplexity tools can be served by any backend.

        Used as the startup gate for registering the Perplexity tools, so it
        checks the environment directly. Returns True when either the direct
        Perplexity backend (SDK installed + PERPLEXITY_API_KEY) or the
        OpenRouter backend (OPENROUTER_API_KEY) is configured. Keys can still
        be overridden at runtime via /api/config once the tools are registered.
        """
        provider = (os.getenv("PERPLEXITY_PROVIDER") or DEFAULT_PERPLEXITY_PROVIDER).strip().lower()
        if provider not in PERPLEXITY_PROVIDERS:
            provider = DEFAULT_PERPLEXITY_PROVIDER

        perplexity_ready = bool(os.getenv("PERPLEXITY_API_KEY")) and PERPLEXITY_AVAILABLE
        openrouter_ready = bool(os.getenv("OPENROUTER_API_KEY"))
        if provider == "perplexity":
            return perplexity_ready
        if provider == "openrouter":
            return openrouter_ready
        return perplexity_ready or openrouter_ready

    def _complete_perplexity(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> _CompletionResult:
        """Run a completion against the direct Perplexity API (synchronous).

        Returns a normalized dict: content, citations, usage, request_id.

        Raises:
            _CompletionError: On any API failure, with a mapped status code.
        """
        client = self._get_client()
        if client is None:
            raise _CompletionError("Perplexity SDK client is not available", 503)

        try:
            completion = client.chat.completions.create(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except RateLimitError as e:
            raise _CompletionError(f"Rate limit exceeded: {e}", 429, rate_limited=True) from e
        except BadRequestError as e:
            raise _CompletionError(f"Bad request: {e}", 400) from e
        except APIStatusError as e:
            raise _CompletionError(f"API error: {e}", 500) from e

        choice = completion.choices[0] if completion.choices else None
        raw_content = choice.message.content if choice and choice.message else ""
        # Ensure content is a string (SDK may return structured content)
        content = str(raw_content) if raw_content else ""

        citations: list[str] = []
        if hasattr(completion, "citations") and completion.citations:
            citations = list(completion.citations)

        usage: dict[str, int] = {}
        if hasattr(completion, "usage") and completion.usage:
            usage = {
                "prompt_tokens": completion.usage.prompt_tokens or 0,
                "completion_tokens": completion.usage.completion_tokens or 0,
                "total_tokens": completion.usage.total_tokens or 0,
            }

        request_id = getattr(completion, "id", None)
        return {
            "content": content,
            "citations": citations,
            "usage": usage,
            "request_id": str(request_id) if request_id is not None else None,
        }

    def _complete_openrouter(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> _CompletionResult:
        """Run a completion against OpenRouter's OpenAI-compatible API (synchronous).

        The bare Sonar model name is mapped to OpenRouter's vendor-prefixed
        slug (e.g. "sonar" -> "perplexity/sonar"). Citations are collected from
        both the Perplexity-style top-level ``citations`` passthrough and
        OpenAI-style ``url_citation`` message annotations.

        Returns a normalized dict: content, citations, usage, request_id.

        Raises:
            _CompletionError: On any HTTP or transport failure.
        """
        try:
            response = requests.post(
                OPENROUTER_API_URL,
                headers={
                    "Authorization": f"Bearer {self.openrouter_api_key}",
                    "Content-Type": "application/json",
                    # Optional attribution headers recommended by OpenRouter
                    "HTTP-Referer": "https://github.com/cotdp/scraper-mcp",
                    "X-Title": "Scraper MCP",
                },
                json={
                    "model": f"{OPENROUTER_MODEL_PREFIX}{model}",
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=OPENROUTER_TIMEOUT_SECONDS,
            )
        except requests.RequestException as e:
            raise _CompletionError(f"OpenRouter connection error: {e}", 502) from e

        if response.status_code == 429:
            raise _CompletionError(
                f"Rate limit exceeded: {response.text[:500]}", 429, rate_limited=True
            )
        if response.status_code == 400:
            raise _CompletionError(f"Bad request: {response.text[:500]}", 400)
        if response.status_code >= 400:
            raise _CompletionError(
                f"OpenRouter API error (HTTP {response.status_code}): {response.text[:500]}",
                response.status_code,
            )

        try:
            data = response.json()
        except ValueError as e:
            raise _CompletionError(f"Invalid JSON from OpenRouter: {e}", 502) from e
        if not isinstance(data, dict):
            raise _CompletionError("Invalid response payload from OpenRouter", 502)

        # OpenRouter can return 200 with an error payload (e.g. moderation).
        error = data.get("error")
        if isinstance(error, dict):
            raise _CompletionError(
                f"OpenRouter error: {error.get('message', 'unknown error')}",
                _http_status_code(error.get("code")),
            )

        choices = data.get("choices")
        first_choice = choices[0] if isinstance(choices, list) and choices else {}
        message = first_choice.get("message") if isinstance(first_choice, dict) else {}
        if not isinstance(message, dict):
            message = {}
        content = str(message.get("content") or "")

        raw_citations = data.get("citations")
        citations = (
            [str(citation) for citation in raw_citations] if isinstance(raw_citations, list) else []
        )
        seen_citations = set(citations)
        annotations = message.get("annotations")
        if isinstance(annotations, list):
            for annotation in annotations:
                if not isinstance(annotation, dict) or annotation.get("type") != "url_citation":
                    continue
                url_citation = annotation.get("url_citation")
                url = url_citation.get("url") if isinstance(url_citation, dict) else None
                if url:
                    citation = str(url)
                    if citation not in seen_citations:
                        citations.append(citation)
                        seen_citations.add(citation)

        usage: dict[str, int] = {}
        raw_usage = data.get("usage")
        if isinstance(raw_usage, dict):
            usage = {
                "prompt_tokens": int(raw_usage.get("prompt_tokens") or 0),
                "completion_tokens": int(raw_usage.get("completion_tokens") or 0),
                "total_tokens": int(raw_usage.get("total_tokens") or 0),
            }

        request_id = data.get("id")
        return {
            "content": content,
            "citations": citations,
            "usage": usage,
            "request_id": str(request_id) if request_id is not None else None,
        }

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> PerplexityResponse:
        """Send a chat completion request to a Sonar model.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            model: Model to use (default: from PERPLEXITY_MODEL env var)
            temperature: Response creativity 0-2 (default: from env var)
            max_tokens: Maximum response tokens (default: from env var)

        Returns:
            PerplexityResponse with content, citations, and usage stats
        """
        # Apply defaults
        model = model or self.default_model
        temperature = temperature if temperature is not None else self.default_temperature
        max_tokens = max_tokens if max_tokens is not None else self.default_max_tokens

        # Extract prompt for metrics logging
        prompt = _extract_prompt(messages)
        metrics_url = f'perplexity://{model}  "{prompt}"'

        backend = self._resolve_backend()
        if backend is None:
            record_request(
                url=metrics_url,
                success=False,
                status_code=503,
                elapsed_ms=0,
                attempts=1,
                error="Perplexity service not available",
                request_type="perplexity",
            )
            return self._error_response("Perplexity service not available", model)

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

        start_time = time.perf_counter()

        try:
            complete = (
                self._complete_openrouter if backend == "openrouter" else self._complete_perplexity
            )
            result = await asyncio.to_thread(complete, messages, model, temperature, max_tokens)

            elapsed_ms = _elapsed_ms(start_time)

            content: str = result["content"]
            citations: list[str] = result["citations"]
            usage: dict[str, int] = result["usage"]

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
                    "provider": backend,
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
                    "request_id": result["request_id"],
                    "elapsed_ms": elapsed_ms,
                    "provider": backend,
                },
            )

        except _CompletionError as e:
            elapsed_ms = _elapsed_ms(start_time)
            record_request(
                url=metrics_url,
                success=False,
                status_code=e.status_code,
                elapsed_ms=elapsed_ms,
                attempts=1,
                error=str(e),
                request_type="perplexity",
            )
            return self._error_response(
                str(e), model, rate_limited=e.rate_limited, provider=backend
            )
        except Exception as e:
            elapsed_ms = _elapsed_ms(start_time)
            record_request(
                url=metrics_url,
                success=False,
                status_code=500,
                elapsed_ms=elapsed_ms,
                attempts=1,
                error=f"Unexpected error: {type(e).__name__}: {e}",
                request_type="perplexity",
            )
            return self._error_response(
                f"Unexpected error: {type(e).__name__}: {e}", model, provider=backend
            )

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
        provider: str | None = None,
    ) -> PerplexityResponse:
        """Create an error response.

        Args:
            error_message: Description of the error
            model: Model that was requested
            rate_limited: Whether this was a rate limit error
            provider: Backend that served (or would have served) the request

        Returns:
            PerplexityResponse with error details in metadata
        """
        metadata: dict[str, Any] = {
            "error": error_message,
        }
        if rate_limited:
            metadata["rate_limited"] = True
        if provider:
            metadata["provider"] = provider

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
