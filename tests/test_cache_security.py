"""Cache serialization, migration, expiry, eviction, and concurrency boundaries."""

from __future__ import annotations

import json
import multiprocessing
import sqlite3
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import pytest

from scraper_mcp.cache_manager import CacheManager
from scraper_mcp.cache_storage import DATABASE_NAME
from scraper_mcp.providers.base import ScrapeResult


def _write_batch(directory: str, worker: int) -> None:
    with CacheManager(cache_dir=directory) as cache:
        for index in range(12):
            key = f"{worker}:{index}"
            value = {"worker": worker, "index": index, "content": "Concurrent 雪"}
            assert cache.set(key, value, expire=60)
            assert cache.get(key) == value


def _pickle_fixture(marker: Path) -> bytes:
    # Synthetic protocol-0 pickle. It would create a marker if deserialized; no
    # pickle reader is imported or used to construct or inspect this fixture.
    return (
        f"cbuiltins\neval\n(S\"__import__('pathlib').Path({str(marker)!r}).touch()\"\ntR."
    ).encode()


def test_legacy_pickle_database_is_untouched_and_never_loaded(tmp_path: Path) -> None:
    marker = tmp_path / "should-not-exist"
    legacy_path = tmp_path / "cache.db"
    with sqlite3.connect(legacy_path) as connection:
        connection.execute("CREATE TABLE Cache (key TEXT, raw INTEGER, value BLOB, mode INTEGER)")
        connection.execute(
            "INSERT INTO Cache VALUES (?, ?, ?, ?)",
            ("unsafe", 1, _pickle_fixture(marker), 4),
        )
    before = legacy_path.read_bytes()
    legacy_file = tmp_path / "legacy.val"
    legacy_file.write_bytes(_pickle_fixture(marker))
    with CacheManager(cache_dir=tmp_path) as cache:
        assert cache.get("unsafe") is None
        assert cache.set("safe", {"content": "new-format"})
        assert cache.get("safe") == {"content": "new-format"}
        cache.clear()
    assert legacy_path.read_bytes() == before
    assert legacy_file.read_bytes() == _pickle_fixture(marker)
    assert not marker.exists()


@pytest.mark.parametrize(
    "record",
    [
        b"pickle",
        "{",
        '{"version":1,"kind":"python/object","value":{"module":"os","call":"system"}}',
        '{"version":1,"kind":"json","value":NaN}',
        '{"version":1,"kind":"json","value":1,"value":2}',
        '{"version":true,"kind":"json","value":"invalid-version"}',
        '{"version":1,"kind":"scrape_result","value":{"url":"https://example.com"}}',
        '{"version":1,"kind":"scrape_result","value":{"url":"https://example.com",'
        '"content":"x","status_code":true,"content_type":null,"metadata":{}}}',
        '{"version":1,"kind":"json","value":' + "[" * 70 + "0" + "]" * 70 + "}",
    ],
)
def test_corrupt_or_hostile_records_are_safe_cache_misses(
    tmp_path: Path, record: str | bytes
) -> None:
    marker = tmp_path / "should-not-exist"
    if record == b"pickle":
        record = _pickle_fixture(marker)
    with CacheManager(cache_dir=tmp_path) as cache:
        assert cache.set("tampered", "original")
        assert cache.set("intact", "available")
        with sqlite3.connect(tmp_path / DATABASE_NAME) as connection:
            connection.execute("UPDATE entries SET payload = ? WHERE key = ?", (record, "tampered"))
        assert cache.get("tampered", default="miss") == "miss"
        assert cache.get("intact") == "available"
        assert list(cache.cache) == ["intact"]
        assert cache.get_stats()["misses"] == 1
    assert not marker.exists()


def test_keys_and_json_paths_never_address_files(tmp_path: Path) -> None:
    with CacheManager(cache_dir=tmp_path / "cache") as cache:
        value = {"filename": "../outside", "mode": "pickle", "value": "ordinary JSON"}
        for key in ("../../outside", "'); DROP TABLE entries; --", "https://example.com/雪"):
            assert cache.set(key, value)
            assert cache.get(key) == value
        assert len(cache.cache) == 3
    assert not (tmp_path / "outside").exists()


def test_new_cache_storage_is_private_and_symlinks_are_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "cache"
    with CacheManager(cache_dir=directory):
        assert directory.stat().st_mode & 0o777 == 0o700
        assert (directory / DATABASE_NAME).stat().st_mode & 0o777 == 0o600
    symlink_dir = tmp_path / "symlink"
    symlink_dir.mkdir()
    target = tmp_path / "untouched"
    target.write_text("Retained")
    (symlink_dir / DATABASE_NAME).symlink_to(target)
    with pytest.raises(ValueError, match="symbolic link"):
        CacheManager(cache_dir=symlink_dir)
    assert target.read_text() == "Retained"


def test_environment_cache_directory_is_private_without_changing_existing_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "new-parent" / "cache"
    monkeypatch.setenv("CACHE_DIR", str(directory))
    with CacheManager() as cache:
        assert cache.cache_dir == directory
        assert directory.stat().st_mode & 0o777 == 0o700
        assert (directory / DATABASE_NAME).stat().st_mode & 0o777 == 0o600

    directory.chmod(0o750)
    with CacheManager():
        assert directory.stat().st_mode & 0o777 == 0o750


@pytest.mark.parametrize("value", [object(), float("nan"), float("inf"), {1: "integer-key"}])
def test_non_json_values_are_rejected_without_replacing_entries(
    tmp_path: Path, value: object
) -> None:
    with CacheManager(cache_dir=tmp_path) as cache:
        assert cache.set("entry", "retained")
        assert cache.set("entry", value) is False
        assert cache.get("entry") == "retained"


def test_scrape_result_roundtrips_without_sharing_mutable_values(tmp_path: Path) -> None:
    original = ScrapeResult(
        url="https://example.com/雪",
        content="<p>Content 雪</p>",
        status_code=200,
        content_type="text/html",
        metadata={"headers": {"Server": "test"}, "elapsed_ms": 1.5, "redirects": [], "ok": True},
    )
    with CacheManager(cache_dir=tmp_path) as cache:
        assert cache.set("result", original, expire=60)
    with CacheManager(cache_dir=tmp_path) as cache:
        restored = cache.get("result")
        assert restored == original
        restored.metadata["headers"]["Server"] = "mutated"
        assert cache.get("result") == original
        with sqlite3.connect(tmp_path / DATABASE_NAME) as connection:
            record = connection.execute("SELECT payload FROM entries").fetchone()[0]
            assert json.loads(record)["kind"] == "scrape_result"


def test_expiry_details_iteration_and_statistics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [1000.0]
    monkeypatch.setattr("scraper_mcp.cache_storage.time.time", lambda: clock[0])
    with CacheManager(cache_dir=tmp_path) as cache:
        assert cache.set("short", {"ttl": True}, expire=10)
        assert cache.set("permanent", "kept")
        assert cache.cache.get("short", expire=True) == ({"ttl": True}, 1010.0)
        assert cache.cache.get("missing", default="miss", expire=True) == ("miss", None)
        clock[0] = 1010.0
        assert list(cache.cache.iterkeys()) == ["permanent"]
        assert len(cache.cache) == 1
        assert cache.expire() == 1
        assert cache.cache.get("short", expire=True) == (None, None)
        assert cache.get_stats()["hits"] == 1
        assert cache.get_stats()["misses"] == 2
        cache.clear()
        assert cache.get_stats()["hits"] == cache.get_stats()["misses"] == 0
        assert cache.get_stats()["size_bytes"] == 0


def test_lru_and_oversized_values_preserve_valid_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [1000.0]
    monkeypatch.setattr("scraper_mcp.cache_storage.time.time", lambda: clock[0])
    with CacheManager(cache_dir=tmp_path, size_limit=300) as cache:
        assert cache.set("one", "x" * 100)
        clock[0] += 1
        assert cache.set("two", "x" * 100)
        clock[0] += 1
        assert cache.get("one") == "x" * 100
        clock[0] += 1
        assert cache.set("three", "x" * 100)
        assert set(cache.cache) == {"one", "three"}
        volume = cache.get_stats()["size_bytes"]
        assert 0 < volume <= 300
        assert cache.set("one", "x" * 1000) is False
        assert set(cache.cache) == {"one", "three"}
        assert cache.get("one") == "x" * 100
        assert cache.get_stats()["size_bytes"] == volume


def test_threads_share_one_manager_safely(tmp_path: Path) -> None:
    with CacheManager(cache_dir=tmp_path) as cache:

        def write_and_read(index: int) -> None:
            assert cache.set(str(index), {"value": index})
            assert cache.get(str(index)) == {"value": index}

        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(write_and_read, range(40)))
        assert len(cache.cache) == 40
        assert cache.get_stats()["hits"] == 40


def test_processes_share_persistent_cache_safely(tmp_path: Path) -> None:
    # Spawn isolates imports and connections, like separate server workers.
    with ProcessPoolExecutor(
        max_workers=3, mp_context=multiprocessing.get_context("spawn")
    ) as executor:
        list(executor.map(_write_batch, [str(tmp_path)] * 3, range(3)))
    with CacheManager(cache_dir=tmp_path) as cache:
        assert len(cache.cache) == 36
        assert cache.get_stats()["hits"] == 36
        assert cache.get_stats()["misses"] == 0
