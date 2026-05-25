from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tracker_assistant.shared.io_utils import load_cached


def _make_items() -> list[dict]:
    return [{"id": "u1", "displayName": "Alice"}, {"id": "u2", "displayName": "Bob"}]


def _write_cache(cache_file: Path, items: list, fetched_at: datetime) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps({"fetched_at": fetched_at.isoformat(), "items": items}, ensure_ascii=False),
        encoding="utf-8",
    )


class TestCacheMiss:
    def test_calls_fetch_fn_when_no_cache_file(self, tmp_path):
        items = _make_items()
        fetch_fn = MagicMock(return_value=items)

        result = load_cached(tmp_path, "users", fetch_fn)

        fetch_fn.assert_called_once()
        assert result == items

    def test_writes_cache_file_after_fetch(self, tmp_path):
        items = _make_items()
        fetch_fn = MagicMock(return_value=items)

        load_cached(tmp_path, "users", fetch_fn)

        cache_file = tmp_path / "cache" / "users.json"
        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert data["items"] == items
        assert "fetched_at" in data

    def test_no_cache_flag_bypasses_existing_cache(self, tmp_path):
        items = _make_items()
        old_items = [{"id": "old"}]
        cache_file = tmp_path / "cache" / "users.json"
        _write_cache(cache_file, old_items, datetime.now(timezone.utc) - timedelta(hours=1))

        fetch_fn = MagicMock(return_value=items)
        result = load_cached(tmp_path, "users", fetch_fn, no_cache=True)

        fetch_fn.assert_called_once()
        assert result == items


class TestCacheHit:
    def test_returns_cached_items_without_fetching(self, tmp_path):
        items = _make_items()
        cache_file = tmp_path / "cache" / "users.json"
        _write_cache(cache_file, items, datetime.now(timezone.utc) - timedelta(hours=1))

        fetch_fn = MagicMock()
        result = load_cached(tmp_path, "users", fetch_fn)

        fetch_fn.assert_not_called()
        assert result == items

    def test_fresh_cache_not_refetched(self, tmp_path):
        items = _make_items()
        cache_file = tmp_path / "cache" / "users.json"
        _write_cache(cache_file, items, datetime.now(timezone.utc) - timedelta(minutes=30))

        fetch_fn = MagicMock()
        result = load_cached(tmp_path, "users", fetch_fn, ttl_hours=24.0)

        fetch_fn.assert_not_called()
        assert result == items


class TestCacheExpired:
    def test_refetches_when_cache_older_than_ttl(self, tmp_path):
        old_items = [{"id": "old"}]
        new_items = _make_items()
        cache_file = tmp_path / "cache" / "users.json"
        _write_cache(cache_file, old_items, datetime.now(timezone.utc) - timedelta(hours=25))

        fetch_fn = MagicMock(return_value=new_items)
        result = load_cached(tmp_path, "users", fetch_fn, ttl_hours=24.0)

        fetch_fn.assert_called_once()
        assert result == new_items

    def test_updates_cache_file_after_refetch(self, tmp_path):
        old_items = [{"id": "old"}]
        new_items = _make_items()
        cache_file = tmp_path / "cache" / "users.json"
        _write_cache(cache_file, old_items, datetime.now(timezone.utc) - timedelta(hours=25))

        fetch_fn = MagicMock(return_value=new_items)
        load_cached(tmp_path, "users", fetch_fn, ttl_hours=24.0)

        data = json.loads(cache_file.read_text())
        assert data["items"] == new_items

    def test_custom_ttl_respected(self, tmp_path):
        items = _make_items()
        cache_file = tmp_path / "cache" / "tags.json"
        _write_cache(cache_file, items, datetime.now(timezone.utc) - timedelta(hours=2))

        fetch_fn = MagicMock(return_value=[])
        # TTL = 1h → 2h old cache should be expired
        result = load_cached(tmp_path, "tags", fetch_fn, ttl_hours=1.0)

        fetch_fn.assert_called_once()


class TestCacheCorruption:
    def test_invalid_json_triggers_refetch(self, tmp_path):
        cache_file = tmp_path / "cache" / "users.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text("not valid json", encoding="utf-8")

        items = _make_items()
        fetch_fn = MagicMock(return_value=items)
        result = load_cached(tmp_path, "users", fetch_fn)

        fetch_fn.assert_called_once()
        assert result == items
