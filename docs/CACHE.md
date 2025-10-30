# HTTP Cache Implementation

This document describes the persistent HTTP caching implementation for the Scraper MCP service using `diskcache`.

## Overview

The scraper includes persistent disk-based HTTP caching to improve performance and reduce redundant network requests. The cache is implemented using `diskcache` with SQLite backend, configured to target approximately **1GB of storage** with automatic eviction.

## Why DiskCache?

- **Provider-Agnostic**: Works with any scraper provider (not just requests)
- **Pure Python**: No C compiler or external dependencies required
- **Thread-Safe & Process-Safe**: Supports concurrent access from multiple processes
- **High Performance**: Matches or exceeds Redis/Memcached for disk-backed scenarios
- **Automatic Management**: Built-in LRU eviction when size limit is reached

## Features

### Core Caching Capabilities

- **Persistent SQLite Cache**: Cache persists across container restarts via Docker volume
- **Configurable Expiration**: Default 1-hour TTL with pattern-based overrides
- **Automatic Size Management**: LRU eviction when 1GB limit reached
- **Statistics Tracking**: Built-in hit/miss tracking
- **Process-Safe**: Concurrent access from multiple containers
- **Context Manager Support**: Safe resource cleanup

### URL Expiration Patterns

```python
# Static assets - 24 hours
*.cdn.com/*              → 86400s
*.static.*/*             → 86400s

# Real-time data - 5 minutes
*api/realtime/*          → 300s
*api/live/*              → 300s

# Default for all other URLs
*                        → 3600s (1 hour)
```

### Cache Management Tools

Three MCP tools available for cache management:

1. **`cache_stats`**: Get cache statistics
   ```json
   {
     "size_bytes": 52428800,
     "size_mb": 50.0,
     "size_limit_mb": 1000.0,
     "utilization_percent": 5.0,
     "hits": 1234,
     "misses": 456,
     "hit_rate": 0.7301,
     "cache_dir": "/app/cache"
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
      memory: 2GB  # 1GB cache + 1GB overhead
    reservations:
      memory: 512M
```

### Cache Parameters

Customize cache behavior when initializing the provider:

```python
provider = RequestsProvider(
    cache_enabled=True,  # Enable/disable caching
)
```

Or configure the cache manager directly:

```python
from scraper_mcp.cache_manager import CacheManager

cache_manager = CacheManager(
    cache_dir="/custom/path",
    size_limit=int(1e9),  # 1GB
    eviction_policy="least-recently-used",
    enable_statistics=True,
)
```

## Implementation Details

### Cache Location

- **Docker**: `/app/cache/` (SQLite database + data files)
- **Development**: `./.cache/` (auto-created if /app/cache not accessible)
- **Files**:
  - `cache.db` - SQLite index
  - Individual cache files for large values

### Cache Behavior

#### What Gets Cached

- **Any Provider**: Works with RequestsProvider, future providers
- **Automatic TTL**: Determined by URL pattern
- **Full Response**: Entire `ScrapeResult` object cached
- **Persistent**: Survives container restarts

#### Cache Key Generation

Cache keys are generated from:
- URL (required)
- Headers (optional, included in key)
- Other parameters (extensible)

Keys are SHA-256 hashes for consistent length.

#### Eviction Policy

- **Strategy**: Least Recently Used (LRU)
- **Trigger**: When cache exceeds 1GB size limit
- **Cull Limit**: Removes up to 10 items per eviction
- **Automatic**: No manual intervention required

### Response Metadata

Every scrape response includes cache metadata:

```python
{
    "from_cache": False,    # Cache hit/miss status
    "attempts": 1,          # Number of attempts
    "retries": 0,           # Number of retries
    # ... other metadata
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
print(f"Cache size: {stats['size_mb']} MB")
print(f"Hit rate: {stats['hit_rate']:.2%}")

# Clear expired entries
result = await cache_clear_expired()
print(f"Removed {result['expired_entries_removed']} entries")

# Clear all cache (use with caution!)
await cache_clear_all()
```

### Using Cache Manager Directly

```python
from scraper_mcp.cache_manager import get_cache_manager

# Get global cache manager
cache_manager = get_cache_manager()

# Get cache key
key = cache_manager.generate_cache_key("https://example.com")

# Check cache
cached_value = cache_manager.get(key)
if cached_value is None:
    # Cache miss - fetch and store
    value = fetch_data()
    ttl = cache_manager.get_ttl_for_url("https://example.com")
    cache_manager.set(key, value, expire=ttl)
```

### Disabling Cache

```python
# Create provider without caching
provider = RequestsProvider(cache_enabled=False)
```

## Cache Monitoring

### Automatic Monitoring

The cache automatically logs warnings when approaching 90% capacity:

```
WARNING: Cache size (950.00 MB) exceeds warning threshold (900 MB).
Automatic eviction will occur on next write.
```

### Manual Monitoring

Check cache size programmatically:

```python
from scraper_mcp.cache import get_cache_stats

stats = get_cache_stats()
print(f"Size: {stats['size_mb']:.2f} MB")
print(f"Utilization: {stats['utilization_percent']:.1f}%")
print(f"Hit rate: {stats['hit_rate']:.2%}")
```

## Performance Considerations

### Benefits

- **Low Latency**: ~25µs for cache hits
- **High Throughput**: Matches Redis for disk-backed scenarios
- **Reduced Network**: No redundant downloads
- **Offline Capability**: Serves cached data when offline
- **Rate Limit Protection**: Fewer requests to origin servers

### Trade-offs

- **Storage**: ~1GB disk space required
- **Staleness**: Default 1-hour cache may serve stale data
- **Write Performance**: ~200µs per cache write
- **Memory Overhead**: ~50-100MB for SQLite and indexes

### Optimization Tips

1. **Adjust TTLs**: Tune expiration times for your use case
2. **Increase Size Limit**: For high-volume scenarios
3. **Disable Statistics**: Minor performance gain if not needed
4. **Use Transactions**: For batch operations

## Best Practices

1. **Cache Clearing**
   - Run `cache_clear_expired()` periodically (e.g., daily)
   - Use `cache_clear_all()` only when necessary
   - Monitor cache size regularly

2. **Monitoring**
   - Check `cache_stats()` to track performance
   - Set up alerts for low hit rates
   - Watch for size warnings in logs

3. **URL Patterns**
   - Customize TTLs in `cache_manager.py` for your use case
   - Use longer TTLs for static content
   - Use shorter TTLs for frequently changing data

4. **Testing**
   - Use `cache_enabled=False` for testing
   - Clear cache between test runs
   - Test cache persistence across restarts

## Architecture

### Module Structure

```
src/scraper_mcp/
├── cache_manager.py            # Core cache manager with diskcache
├── cache.py                    # Utility functions
├── providers/
│   └── requests_provider.py    # Provider with cache integration
└── server.py                   # Cache management tools
```

### Key Components

- **`CacheManager`**: Core caching logic using diskcache
- **`get_cache_manager()`**: Global singleton instance
- **Provider Integration**: Automatic cache lookup/storage
- **MCP Tools**: Expose cache management via MCP protocol

### Cache Storage

```
cache/
├── cache.db               # SQLite index
├── 00/                    # Cache data shards
├── 01/
└── ...
```

## Troubleshooting

### Cache Not Working

1. Check cache is enabled: `provider.cache_enabled`
2. Verify cache directory exists and is writable
3. Check logs for cache initialization messages
4. Ensure diskcache is installed: `uv pip show diskcache`

### Cache Too Large

```python
# Option 1: Clear expired entries
await cache_clear_expired()

# Option 2: Clear all cache
await cache_clear_all()

# Option 3: Increase size limit
cache_manager = CacheManager(size_limit=int(2e9))  # 2GB
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
docker volume inspect cache_data
```

### Low Hit Rate

1. Check TTLs are appropriate for your workload
2. Verify cache keys are consistent
3. Monitor for frequent cache clears
4. Consider increasing cache size limit

## Testing

### Run Cache Tests

```bash
# All cache tests
uv run pytest tests/test_cache.py -v

# Specific test class
uv run pytest tests/test_cache.py::TestCacheManager -v

# With coverage
uv run pytest tests/test_cache.py --cov=scraper_mcp.cache_manager
```

### Test Coverage

Current cache test coverage: **16 tests, all passing**

```
tests/test_cache.py::TestCacheManager                    8 tests
tests/test_cache.py::TestCacheManagerIntegration         2 tests
tests/test_cache.py::TestCacheUtilityFunctions           3 tests
tests/test_cache.py::TestCacheContextManager             1 test
tests/test_cache.py::TestCachePersistence                1 test
tests/test_cache.py::TestCacheSizeManagement             1 test
```

## Future Enhancements

Potential improvements for future iterations:

1. **Cache Warming**: Pre-populate cache with commonly requested URLs
2. **Distributed Cache**: Share cache across multiple container instances
3. **Compression**: Enable cache compression to reduce storage
4. **Smart TTLs**: ML-based TTL prediction
5. **Cache Analytics**: Export metrics to Prometheus/Grafana
6. **Conditional Requests**: ETags and Last-Modified headers
7. **Cache Partitioning**: Separate caches for different use cases

## Comparison with requests-cache

| Feature | diskcache | requests-cache |
|---------|-----------|----------------|
| Provider Support | Any provider | requests only |
| Backend | SQLite (optimized) | SQLite or others |
| Performance | ~25µs reads | ~50µs reads |
| Process-Safe | Yes (built-in) | Limited |
| Size Management | Automatic LRU | Manual |
| Statistics | Built-in | Basic |
| Dependencies | None | cattrs, url-normalize |

## References

- [DiskCache Documentation](https://grantjenks.com/docs/diskcache/)
- [DiskCache GitHub](https://github.com/grantjenks/python-diskcache)
- [SQLite Performance](https://www.sqlite.org/performance.html)
- [HTTP Caching Best Practices](https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching)
