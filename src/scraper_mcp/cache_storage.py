"""SQLite cache with a closed JSON format; legacy pickle caches are never opened."""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scraper_mcp.providers.base import ScrapeResult

logger = logging.getLogger(__name__)
DATABASE_NAME = "cache-v1.sqlite3"


def _validate_json(value: object, depth: int = 0) -> None:
    """Accept JSON primitives only, without adapters or executable object hooks."""
    if depth > 64:
        raise ValueError("Cache value exceeds the JSON nesting limit")
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _validate_json(item, depth + 1)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _validate_json(item, depth + 1)
        return
    raise ValueError("Cache values must contain only finite JSON primitives")


def _scrape_result(value: object) -> ScrapeResult:
    """Decode only the known scrape result schema, never arbitrary Python types."""
    from scraper_mcp.providers.base import ScrapeResult

    fields = {"url", "content", "status_code", "content_type", "metadata"}
    if (
        not isinstance(value, dict)
        or value.keys() != fields
        or type(value["url"]) is not str
        or type(value["content"]) is not str
        or type(value["status_code"]) is not int
        or not (value["content_type"] is None or type(value["content_type"]) is str)
        or type(value["metadata"]) is not dict
    ):
        raise ValueError("Invalid cached scrape result")
    return ScrapeResult(**value)


def _encode(value: Any) -> str:
    from scraper_mcp.providers.base import ScrapeResult

    kind = "json"
    if type(value) is ScrapeResult:
        kind = "scrape_result"
        value = {
            "url": value.url,
            "content": value.content,
            "status_code": value.status_code,
            "content_type": value.content_type,
            "metadata": value.metadata,
        }
        _scrape_result(value)
    envelope = {"version": 1, "kind": kind, "value": value}
    _validate_json(envelope)
    return json.dumps(
        envelope,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON key in cache record")
        value[key] = item
    return value


def _decode(payload: object) -> Any:
    if type(payload) is not str:
        raise ValueError("Cache records must contain JSON text")
    envelope = json.loads(payload, object_pairs_hook=_unique_object)
    _validate_json(envelope)
    if (
        not isinstance(envelope, dict)
        or envelope.keys() != {"version", "kind", "value"}
        or type(envelope["version"]) is not int
        or envelope["version"] != 1
    ):
        raise ValueError("Invalid cache record envelope")
    if envelope["kind"] == "json":
        return envelope["value"]
    if envelope["kind"] == "scrape_result":
        return _scrape_result(envelope["value"])
    raise ValueError("Unsupported cache record type")


class JsonCache:
    """Process/thread-safe TTL/LRU cache using transactions and JSON text.

    The size limit bounds encoded keys and values, excluding SQLite page/index/WAL
    overhead. Oversized entries are rejected before any existing entries change.
    A new filename deliberately leaves legacy diskcache databases/files untouched.
    Connections are scoped to operations, so none are shared across threads/forks.
    """

    def __init__(
        self,
        directory: str | Path,
        size_limit: int,
        eviction_policy: str = "least-recently-used",
        statistics: bool = True,
    ) -> None:
        if size_limit <= 0:
            raise ValueError("Cache size_limit must be positive")
        if eviction_policy != "least-recently-used":
            raise ValueError("Only least-recently-used cache eviction is supported")
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.directory / DATABASE_NAME
        self.size_limit = size_limit
        self._statistics = statistics
        if self.path.is_symlink():
            raise ValueError("The cache database must not be a symbolic link")
        try:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass  # Existing cache data and its ownership/permissions remain untouched.
        else:
            os.close(descriptor)
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA auto_vacuum=FULL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    expires_at REAL,
                    accessed_at REAL NOT NULL,
                    size INTEGER NOT NULL CHECK (size >= 0)
                );
                CREATE INDEX IF NOT EXISTS entries_expiry ON entries(expires_at);
                CREATE INDEX IF NOT EXISTS entries_lru ON entries(accessed_at);
                CREATE TABLE IF NOT EXISTS statistics (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    hits INTEGER NOT NULL,
                    misses INTEGER NOT NULL
                );
                INSERT OR IGNORE INTO statistics VALUES (1, 0, 0);
                """
            )

    def _connect(self, retry: bool = True) -> sqlite3.Connection:
        if self.path.is_symlink():
            raise ValueError("The cache database must not be a symbolic link")
        connection = sqlite3.connect(self.path, timeout=10 if retry else 0, isolation_level=None)
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA journal_size_limit=4194304")
        return connection

    @contextmanager
    def _transaction(self, retry: bool = True) -> Iterator[sqlite3.Connection]:
        with closing(self._connect(retry)) as connection, connection:
            # Serialize read/modify/write operations across processes, including
            # hit counters and eviction. sqlite3's busy timeout bounds lock waits.
            connection.execute("BEGIN IMMEDIATE")
            yield connection

    def _record_access(self, connection: sqlite3.Connection, hit: bool) -> None:
        if self._statistics:
            connection.execute(
                "UPDATE statistics SET hits = hits + ?, misses = misses + ? WHERE id = 1",
                (int(hit), int(not hit)),
            )

    def get(self, key: str, default: Any = None, retry: bool = True, expire: bool = False) -> Any:
        with self._transaction(retry) as connection:
            row = connection.execute(
                "SELECT payload, expires_at FROM entries WHERE key = ?", (key,)
            ).fetchone()
            value, expires_at = default, None
            hit = False
            now = time.time()
            if row is not None:
                payload, expires_at = row
                valid_expiry = expires_at is None or (
                    type(expires_at) in (int, float)
                    and math.isfinite(expires_at)
                    and expires_at > now
                )
                if valid_expiry:
                    try:
                        value = _decode(payload)
                        hit = True
                    except (ValueError, TypeError, RecursionError):
                        logger.warning("Ignoring an invalid JSON cache record")
                if hit:
                    connection.execute(
                        "UPDATE entries SET accessed_at = ? WHERE key = ?", (now, key)
                    )
                else:
                    connection.execute("DELETE FROM entries WHERE key = ?", (key,))
                    expires_at = None
            self._record_access(connection, hit)
            return (value, expires_at) if expire else value

    def set(self, key: str, value: Any, expire: int | None = None, retry: bool = True) -> bool:
        if type(key) is not str:
            raise ValueError("Cache keys must be strings")
        payload = _encode(value)
        size = len(key.encode("utf-8")) + len(payload.encode("utf-8"))
        if size > self.size_limit:
            return False
        if expire is not None and (type(expire) not in (int, float) or not math.isfinite(expire)):
            raise ValueError("Cache expiration must be a finite number of seconds")
        now = time.time()
        expires_at = None if expire is None else now + expire
        with self._transaction(retry) as connection:
            connection.execute("DELETE FROM entries WHERE expires_at <= ?", (now,))
            connection.execute(
                """INSERT INTO entries (key, payload, expires_at, accessed_at, size)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET payload = excluded.payload,
                       expires_at = excluded.expires_at, accessed_at = excluded.accessed_at,
                       size = excluded.size""",
                (key, payload, expires_at, now, size),
            )
            total = connection.execute("SELECT COALESCE(SUM(size), 0) FROM entries").fetchone()[0]
            if total > self.size_limit:
                # Never evict the just-written value on tied wall-clock timestamps.
                victims = connection.execute(
                    "SELECT key, size FROM entries WHERE key != ? ORDER BY accessed_at, key",
                    (key,),
                ).fetchall()
                for old_key, old_size in victims:
                    connection.execute("DELETE FROM entries WHERE key = ?", (old_key,))
                    total -= old_size
                    if total <= self.size_limit:
                        break
        return True

    def delete(self, key: str, retry: bool = True) -> bool:
        with self._transaction(retry) as connection:
            return connection.execute("DELETE FROM entries WHERE key = ?", (key,)).rowcount > 0

    def clear(self, retry: bool = True) -> int:
        with self._transaction(retry) as connection:
            return connection.execute("DELETE FROM entries").rowcount

    def expire(self) -> int:
        with self._transaction() as connection:
            return connection.execute(
                "DELETE FROM entries WHERE expires_at <= ?", (time.time(),)
            ).rowcount

    def stats(self, enable: bool | None = None, reset: bool = False) -> tuple[int, int]:
        with self._transaction() as connection:
            hits, misses = connection.execute(
                "SELECT hits, misses FROM statistics WHERE id = 1"
            ).fetchone()
            if reset:
                connection.execute("UPDATE statistics SET hits = 0, misses = 0 WHERE id = 1")
            if enable is not None:
                self._statistics = enable
            return int(hits), int(misses)

    def volume(self) -> int:
        """Return encoded key/value bytes; database/index/WAL overhead is excluded."""
        with self._transaction() as connection:
            return int(
                connection.execute("SELECT COALESCE(SUM(size), 0) FROM entries").fetchone()[0]
            )

    def iterkeys(self) -> Iterator[str]:
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT key FROM entries WHERE expires_at IS NULL OR expires_at > ? ORDER BY key",
                (time.time(),),
            ).fetchall()
        return iter(row[0] for row in rows)

    def __iter__(self) -> Iterator[str]:
        return self.iterkeys()

    def __len__(self) -> int:
        with self._transaction() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM entries WHERE expires_at IS NULL OR expires_at > ?",
                    (time.time(),),
                ).fetchone()[0]
            )

    def close(self) -> None:
        """Connections close after each operation; retained for manager compatibility."""
