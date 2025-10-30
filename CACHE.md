# HTTP Cache Implementation

This document describes the persistent HTTP caching implementation for the Scraper MCP service using `requests-cache`.

## Overview

The scraper now includes persistent HTTP caching to improve performance and reduce redundant network requests. The cache is implemented using SQLite and configured to target approximately **1GB of storage**.

## Features

### Core Caching Capabilities

- **Persistent SQLite Cache**: Cache persists across container restarts via Docker volume
- **Configurable Expiration**: Default 1-hour TTL with pattern-based overrides
- **Cache Control Compliance**: Respects server `Cache-Control` headers
- **Stale-if-Error**: Serves cached responses when requests fail
- **Automatic Size Monitoring**: Logs warnings at 90% capacity (900MB)
- **Pattern-Based Expiration**: Different TTLs for different URL patterns

### URL Expiration Patterns

```python
# Static assets never expire
*.cdn.com/static/*       → Never expire (-1)
*.cloudfront.net/*       → Never expire (-1)

# Real-time data expires quickly
*api*/realtime/*         → 5 minutes (300s)
*api*/live/*             → 5 minutes (300s)

# Default for all other URLs
*                        → 1 hour (3600s)
```

### Cache Management Tools

Three new MCP tools are available for cache management:

1. **`cache_stats`**: Get cache statistics
   ```json
   {
     "total_responses": 1234,
     "cache_size_bytes": 52428800,
     "cache_size_mb": 50.0,
     "cache_path": "/app/cache/scrape_cache.sqlite"
   }
   ```

2. **`cache_clear_expired`**: Remove expired entries
   ```json
   {
     "status": "success",
     "expired_entries_removed": 42
   }
   ```

3. **`cache_clear_all`**: Clear all cached entries
   ```json
   {
     "status": "success",
     "message": "All cache entries cleared"
   }
   ```

## Configuration

### Environment Variables

- `CACHE_DIR`: Cache directory path (default: `/app/cache`)
  - In Docker: `/app/cache` (mounted volume)
  - In development: `.cache/` (local directory, auto-created)

### Docker Configuration

#### Volume Mount

```yaml
volumes:
  - cache_data:/app/cache
```

#### Memory Limits

```yaml
deploy:
  resources:
    limits:
      memory: 1536M  # 1GB cache + 512MB overhead
    reservations:
      memory: 512M
```

### Cache Parameters

Customize cache behavior when initializing the provider:

```python
provider = RequestsProvider(
    cache_enabled=True,           # Enable/disable caching
    cache_expire_after=3600,      # Default expiration (seconds)
)
```

## Implementation Details

### Cache Location

- **Docker**: `/app/cache/scrape_cache.sqlite`
- **Development**: `./.cache/scrape_cache.sqlite`
- **Fallback**: Automatically uses local `.cache/` if `/app/cache` is not accessible

### Cache Behavior

#### What Gets Cached

- **HTTP Methods**: GET, HEAD
- **Status Codes**: 200, 203, 300, 301, 308
- **Respects**: Server Cache-Control headers
- **Ignores**: Authentication parameters in cache keys

#### What Doesn't Get Cached

- **Ignored Parameters**: `api_key`, `access_token`, `auth`, `key`, `token`
- **Error Responses**: 4xx, 5xx status codes (except cached via stale-if-error)
- **Non-HTTP Schemes**: FTP, file://, etc.

### Response Metadata

Every scrape response includes cache metadata:

```python
{
    "from_cache": False,           # Cache hit/miss status
    "cache_expires": "2025-10-30T15:30:00",  # Expiration timestamp
    "attempts": 1,                  # Number of attempts
    "retries": 0                    # Number of retries
}
```

## Usage Examples

### Basic Scraping (Automatic Caching)

```python
# First request - cache miss
result1 = await scrape_url("https://example.com")
print(result1.metadata["from_cache"])  # False

# Second request - cache hit
result2 = await scrape_url("https://example.com")
print(result2.metadata["from_cache"])  # True
```

### Cache Management

```python
# Check cache stats
stats = await cache_stats()
print(f"Cache size: {stats['cache_size_mb']} MB")

# Clear expired entries
result = await cache_clear_expired()
print(f"Removed {result['expired_entries_removed']} entries")

# Clear all cache (use with caution!)
await cache_clear_all()
```

### Disabling Cache

```python
# Create provider without caching
provider = RequestsProvider(cache_enabled=False)
```

## Cache Monitoring

### Automatic Monitoring

The cache automatically logs warnings when it exceeds 900MB (90% of target):

```
WARNING: Cache size (950.00 MB) exceeds warning threshold (900 MB).
Consider clearing expired entries.
```

### Manual Monitoring

Check cache size programmatically:

```python
from scraper_mcp.cache import get_cache_size

size_bytes = get_cache_size()
size_mb = size_bytes / (1024 * 1024)
print(f"Cache size: {size_mb:.2f} MB")
```

## Performance Considerations

### Benefits

- **Reduced Latency**: Cache hits return instantly (no network delay)
- **Reduced Bandwidth**: No redundant downloads
- **Rate Limit Protection**: Fewer requests to origin servers
- **Offline Capability**: Stale cache serves responses when offline

### Trade-offs

- **Storage**: ~1GB disk space required
- **Staleness**: Default 1-hour cache may serve stale data
- **Memory**: SQLite cache adds ~50-100MB memory overhead

## Best Practices

1. **Cache Clearing**
   - Run `cache_clear_expired()` periodically (e.g., daily)
   - Use `cache_clear_all()` only when necessary (resets all cached data)

2. **Monitoring**
   - Check `cache_stats()` regularly to monitor cache size
   - Set up alerts for cache size warnings

3. **URL Patterns**
   - Adjust expiration patterns in `cache.py` for your use case
   - Use `-1` for URLs that never change
   - Use short TTLs (300s) for frequently changing data

4. **Testing**
   - Use `cache_enabled=False` for testing to avoid cache interference
   - Clear cache between test runs for consistency

## Architecture

### Module Structure

```
src/scraper_mcp/
├── cache.py                    # Cache configuration and utilities
├── providers/
│   └── requests_provider.py    # Provider with cache integration
└── server.py                   # Cache management tools
```

### Key Components

- **`cache.py`**: Core cache configuration and management functions
- **`RequestsProvider`**: Integrates `CachedSession` for HTTP requests
- **MCP Tools**: Expose cache management via MCP protocol

### Cache Storage

```
cache/
└── scrape_cache.sqlite       # Main cache database
    ├── .sqlite-shm           # Shared memory file
    └── .sqlite-wal           # Write-ahead log
```

## Troubleshooting

### Cache Not Working

1. Check cache is enabled: `provider.cache_enabled`
2. Verify cache directory exists and is writable
3. Check logs for cache initialization messages

### Cache Too Large

```python
# Option 1: Clear expired entries
await cache_clear_expired()

# Option 2: Clear all cache
await cache_clear_all()

# Option 3: Reduce default expiration
provider = RequestsProvider(cache_expire_after=1800)  # 30 minutes
```

### Cache Not Persisting (Docker)

Ensure volume is mounted in docker-compose.yml:

```yaml
volumes:
  - cache_data:/app/cache
```

Check volume exists:

```bash
docker volume ls | grep cache_data
```

## Testing

### Run Cache Tests

```bash
# All cache tests
uv run pytest tests/test_cache.py -v

# Specific test
uv run pytest tests/test_cache.py::TestCacheConfiguration -v
```

### Test Coverage

Current cache test coverage: **97%**

```
Name                    Stmts   Miss  Cover
--------------------------------------------
src/scraper_mcp/cache.py   65      2    97%
```

## Future Enhancements

Potential improvements for future iterations:

1. **Cache Warming**: Pre-populate cache with commonly requested URLs
2. **Cache Metrics**: Export Prometheus metrics for monitoring
3. **Distributed Cache**: Support Redis backend for multi-instance deployments
4. **Intelligent Expiration**: ML-based TTL prediction based on content volatility
5. **Compression**: Enable cache compression to reduce storage requirements
6. **Cache Partitioning**: Separate caches for different use cases

## References

- [requests-cache Documentation](https://requests-cache.readthedocs.io/)
- [SQLite Performance Tuning](https://www.sqlite.org/performance.html)
- [HTTP Caching Best Practices](https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching)
