# Use Python 3.12 slim image as base
FROM python:3.12-slim

# Build-time proxy arguments (for package installation)
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy

# Set working directory
WORKDIR /app

# Install system dependencies for lxml
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files and README (required for package build)
COPY pyproject.toml README.md ./

# Copy application code (needed before editable install)
COPY src/ ./src/

# Install package and dependencies using uv
RUN uv pip install --system -e .

# Create cache directory with proper permissions
RUN mkdir -p /app/cache && chmod 777 /app/cache

# Create non-root user for security
RUN groupadd -r scraper && useradd -r -g scraper scraper

# Change ownership of app and cache directories
RUN chown -R scraper:scraper /app

# Switch to non-root user
USER scraper

# Expose default port
EXPOSE 8000

# Set Python path
ENV PYTHONPATH=/app

# Set cache directory environment variable
ENV CACHE_DIR=/app/cache

# Run the server
CMD ["python", "-m", "scraper_mcp"]
