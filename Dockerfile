# Use Python 3.12 slim image as base
FROM python:3.15-slim

# Build-time proxy arguments (for package installation)
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy

# Set working directory
WORKDIR /app

# Apply available base-image fixes and install Chromium runtime libraries.
# Locked lxml wheels include their native libraries; build headers are unnecessary.
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    # Chromium dependencies for Playwright
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Pin uv so release builds use a reproducible installer.
COPY --from=ghcr.io/astral-sh/uv:0.13.3 /uv /usr/local/bin/uv

# uv installs the runtime environment. Remove unused bootstrap pip and its
# vendored dependencies so their advisories do not ship in the production image.
RUN /usr/local/bin/python -m pip uninstall -y pip

# Copy dependency metadata first so dependency installation remains cacheable.
COPY pyproject.toml uv.lock README.md ./

# Install the exact locked production dependency graph without the project itself.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"
RUN uv sync --frozen --no-dev --extra perplexity --extra playwright --no-install-project

# Set Playwright browser path BEFORE install so browsers go to correct location
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install Playwright browsers (Chromium only to minimize image size)
# Run as root to install system-wide, users will access via shared browser
RUN playwright install chromium --with-deps && \
    chmod -R 755 /ms-playwright

# Copy application code last (invalidates fewer layers on source changes), then
# install the project against the already-synchronized locked environment.
COPY src/ ./src/
RUN uv sync --frozen --no-dev --extra perplexity --extra playwright

# Create cache directory with proper permissions
RUN mkdir -p /app/cache && chmod 700 /app/cache

# Create non-root user for security
RUN groupadd -r scraper && useradd -r -g scraper scraper

# Keep application code and installed dependencies owned by root.
# Only persistent cache data needs to be writable by the service.
RUN chown scraper:scraper /app/cache

# Playwright stores browsers in /root/.cache by default, make accessible
# The --with-deps flag installs to system location, so this may not be needed
# but we ensure the ms-playwright cache is accessible
RUN mkdir -p /home/scraper/.cache && chown -R scraper:scraper /home/scraper

# Switch to non-root user
USER scraper

# Expose default port
EXPOSE 8000

# Set Python path
ENV PYTHONPATH=/app

# Set cache directory environment variable
ENV CACHE_DIR=/app/cache

# Run the server
CMD ["python", "-m", "scraper_mcp", "streamable-http", "0.0.0.0", "8000"]
