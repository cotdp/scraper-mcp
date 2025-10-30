# Use Python 3.12 slim image as base
FROM python:3.12-slim

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

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies using uv
RUN uv pip install --system -e .

# Copy application code
COPY src/ ./src/

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
