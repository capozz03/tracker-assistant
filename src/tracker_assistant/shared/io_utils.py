from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


def load_env(root: Path) -> dict[str, str]:
    """Read KEY=VALUE pairs from .env in root, falling back to environment variables."""
    env_path = root / ".env"
    values: dict[str, str] = {}
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    # environment variables take precedence over .env
    for key in list(values):
        if key in os.environ:
            values[key] = os.environ[key]
    return values


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cached(
    root: Path,
    key: str,
    fetch_fn: Callable[[], list[dict[str, Any]]],
    *,
    ttl_hours: float = 24.0,
    no_cache: bool = False,
) -> list[dict[str, Any]]:
    """Load items from a TTL-based JSON cache or fetch fresh data.

    Cache file: <root>/cache/<key>.json
    Format: {"fetched_at": "<ISO8601>", "items": [...]}
    """
    cache_dir = root / "cache"
    cache_file = cache_dir / f"{key}.json"

    if not no_cache and cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(data["fetched_at"])
            now = datetime.now(timezone.utc)
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            age_hours = (now - fetched_at).total_seconds() / 3600
            if age_hours < ttl_hours:
                logger.debug("cache hit: %s (age=%.0fh)", key, age_hours)
                return data["items"]
            logger.debug("cache expired: %s (age=%.0fh >= ttl=%.0fh) — fetching from API", key, age_hours, ttl_hours)
        except (KeyError, ValueError, OSError) as exc:
            logger.debug("cache read error for %s: %s — fetching from API", key, exc)

    logger.debug("cache miss: %s — fetching from API", key)
    items = fetch_fn()

    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }
    try:
        cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("cached %d %s items", len(items), key)
    except OSError as exc:
        logger.warning("failed to write cache for %s: %s", key, exc)

    return items
