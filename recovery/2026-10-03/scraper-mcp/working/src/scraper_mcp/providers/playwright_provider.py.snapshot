"""Playwright-based provider for JavaScript rendering support."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import TYPE_CHECKING, Any

from scraper_mcp.providers.base import ScrapeResult, ScraperProvider

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Playwright

# Configure logging
logger = logging.getLogger(__name__)


class BrowserPoolManager:
    """Singleton manager for Playwright browser instance.

    Manages a single browser instance with multiple isolated contexts
    for efficient resource usage. Uses semaphore to control concurrency.
    """

    _instance: BrowserPoolManager | None = None
    _lock: asyncio.Lock | None = None
    _initialized: bool
    _browser: Browser | None
    _playwright: Playwright | None

    def __new__(cls) -> BrowserPoolManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self._initialized = True
        self._browser = None
        self._playwright = None
        self._init_lock = asyncio.Lock()

        # Configuration from environment
        self.max_contexts = int(os.getenv("PLAYWRIGHT_MAX_CONTEXTS", "5"))
        self.timeout = int(os.getenv("PLAYWRIGHT_TIMEOUT", "30000"))
        disable_gpu_env = os.getenv("PLAYWRIGHT_DISABLE_GPU", "true").lower()
        self.disable_gpu = disable_gpu_env in ("true", "1", "yes")

        # Semaphore to limit concurrent contexts
        self._semaphore: asyncio.Semaphore | None = None

        # Track active contexts for cleanup
        self._active_contexts: int = 0

        logger.info(
            f"BrowserPoolManager initialized (max_contexts={self.max_contexts}, "
            f"timeout={self.timeout}ms)"
        )

    async def _ensure_browser(self) -> None:
        """Lazily initialize browser on first use."""
        if self._browser is not None:
            return

        async with self._init_lock:
            # Double-check after acquiring lock
            if self._browser is not None:
                return

            try:
                from playwright.async_api import async_playwright

                logger.info("Starting Playwright browser...")

                self._playwright = await async_playwright().start()

                # Build browser launch arguments
                args = [
                    "--disable-dev-shm-usage",  # Reduce memory in containers
                    "--no-sandbox",  # Required for some container environments
                ]

                if self.disable_gpu:
                    args.append("--disable-gpu")

                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=args,
                )

                # Initialize semaphore after browser is ready
                self._semaphore = asyncio.Semaphore(self.max_contexts)

                logger.info("Playwright browser started successfully")

            except ImportError:
                logger.error(
                    "Playwright not installed. Install with: "
                    "pip install playwright && playwright install chromium"
                )
                raise
            except Exception as e:
                logger.error(f"Failed to start Playwright browser: {e}")
                raise

    async def acquire_context(self) -> BrowserContext:
        """Acquire a new browser context with semaphore control.

        Returns:
            A Playwright browser context

        Raises:
            RuntimeError: If browser is not available
        """
        await self._ensure_browser()

        if self._semaphore is None or self._browser is None:
            raise RuntimeError("Browser not initialized")

        await self._semaphore.acquire()
        self._active_contexts += 1

        try:
            user_agent = (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )
            context = await self._browser.new_context(user_agent=user_agent)
            return context
        except Exception:
            self._active_contexts -= 1
            self._semaphore.release()
            raise

    async def release_context(self, context: BrowserContext) -> None:
        """Release a browser context back to the pool.

        Args:
            context: The Playwright browser context to release
        """
        try:
            await context.close()
        except Exception as e:
            logger.warning(f"Error closing browser context: {e}")
        finally:
            self._active_contexts -= 1
            if self._semaphore:
                self._semaphore.release()

    async def shutdown(self) -> None:
        """Gracefully shutdown the browser."""
        if self._browser:
            logger.info("Shutting down Playwright browser...")
            try:
                await self._browser.close()
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")
            self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.warning(f"Error stopping playwright: {e}")
            self._playwright = None

        logger.info("Playwright browser shutdown complete")

    @property
    def is_initialized(self) -> bool:
        """Check if browser is initialized."""
        return self._browser is not None

    @property
    def active_contexts(self) -> int:
        """Get count of active contexts."""
        return self._active_contexts


# Global browser pool instance
_browser_pool: BrowserPoolManager | None = None


def get_browser_pool() -> BrowserPoolManager:
    """Get the global browser pool manager instance."""
    global _browser_pool
    if _browser_pool is None:
        _browser_pool = BrowserPoolManager()
    return _browser_pool


class PlaywrightProvider(ScraperProvider):
    """Web scraper using Playwright for JavaScript rendering.

    Uses a shared browser instance with isolated contexts for
    efficient resource usage while providing full JavaScript support.
    """

    def __init__(
        self,
        timeout: int = 30000,
        wait_until: str = "networkidle",
    ) -> None:
        """Initialize the Playwright provider.

        Args:
            timeout: Page load timeout in milliseconds (default: 30000)
            wait_until: When to consider navigation complete.
                Options: "load", "domcontentloaded", "networkidle" (default)
        """
        self.timeout = timeout
        self.wait_until = wait_until
        self._pool = get_browser_pool()

    def supports_url(self, url: str) -> bool:
        """Check if this provider supports the given URL.

        Args:
            url: The URL to check

        Returns:
            True if the URL uses http or https scheme
        """
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            return parsed.scheme in ("http", "https")
        except (ValueError, TypeError, AttributeError):
            return False

    async def scrape(self, url: str, **kwargs: Any) -> ScrapeResult:
        """Scrape content from a URL using Playwright with JavaScript rendering.

        Args:
            url: The URL to scrape
            **kwargs: Additional options
                - timeout: Page load timeout in seconds (will be converted to ms)
                - wait_until: Navigation wait strategy
                - wait_for_selector: CSS selector to wait for before extracting content

        Returns:
            ScrapeResult containing the rendered HTML content and metadata

        Raises:
            Exception: If the page fails to load or render
        """
        # Convert timeout from seconds to milliseconds (API uses seconds)
        timeout_seconds = kwargs.get("timeout", 30)
        timeout = timeout_seconds * 1000 if timeout_seconds < 1000 else timeout_seconds
        wait_until = kwargs.get("wait_until", self.wait_until)
        wait_for_selector = kwargs.get("wait_for_selector")

        start_time = time.time()
        context = None
        page = None

        try:
            # Acquire browser context from pool
            context = await self._pool.acquire_context()
            page = await context.new_page()

            # Set page timeout
            page.set_default_timeout(timeout)

            # Navigate to URL
            response = await page.goto(url, wait_until=wait_until)

            # Wait for specific selector if provided
            if wait_for_selector:
                await page.wait_for_selector(wait_for_selector, timeout=timeout)

            # Get final URL (after redirects)
            final_url = page.url

            # Extract rendered HTML content
            content = await page.content()

            # Calculate timing
            elapsed_ms = (time.time() - start_time) * 1000

            # Get response status code (may be None for some navigations)
            status_code = response.status if response else 200

            # Get content type from response headers
            content_type = None
            if response:
                headers = response.headers
                content_type = headers.get("content-type")

            # Build metadata
            metadata: dict[str, Any] = {
                "elapsed_ms": elapsed_ms,
                "rendered_js": True,
                "wait_until": wait_until,
                "final_url": final_url,
                "from_cache": False,
                "attempts": 1,
                "retries": 0,
            }

            if wait_for_selector:
                metadata["wait_for_selector"] = wait_for_selector

            return ScrapeResult(
                url=final_url,
                content=content,
                status_code=status_code,
                content_type=content_type,
                metadata=metadata,
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(f"Playwright scrape failed for {url}: {e}")

            # Re-raise with context for better error messages
            raise RuntimeError(f"Playwright failed to render {url}: {e}") from e

        finally:
            # Clean up page and context
            if page:
                try:
                    await page.close()
                except Exception:
                    pass

            if context:
                await self._pool.release_context(context)


# Global Playwright provider instance (lazy initialized)
_playwright_provider: PlaywrightProvider | None = None


def get_playwright_provider() -> PlaywrightProvider:
    """Get the global Playwright provider instance."""
    global _playwright_provider
    if _playwright_provider is None:
        _playwright_provider = PlaywrightProvider()
    return _playwright_provider


def is_playwright_available() -> bool:
    """Check if Playwright is installed and available.

    Returns:
        True if Playwright can be imported
    """
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


async def shutdown_browser_pool() -> None:
    """Shutdown the browser pool gracefully.

    Call this on server shutdown to clean up resources.
    """
    global _browser_pool
    if _browser_pool and _browser_pool.is_initialized:
        await _browser_pool.shutdown()
