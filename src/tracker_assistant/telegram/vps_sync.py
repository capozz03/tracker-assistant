from __future__ import annotations

"""VPS codebase synchronisation: rsync over SSH or git clone/pull."""

import enum
import logging
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Timestamp file written after each successful sync
_SYNC_TIMESTAMP = ".sync_timestamp"
# Lockfile present while a sync is in progress
_SYNC_LOCK = ".sync_in_progress"

# Patterns for strategy detection
_SSH_PATTERN = re.compile(
    r"^(?:[^@:/]+@)?[a-zA-Z0-9][\w.\-]*:[/\w].*"
)
_GIT_PATTERN = re.compile(
    r"(?:git\+ssh://|git\+https://|https?://|git@).*|.*\.git$"
)


class SyncStrategy(enum.Enum):
    LOCAL = "local"
    SSH_RSYNC = "ssh_rsync"
    GIT_CLONE = "git_clone"


def detect_strategy(path_spec: str) -> SyncStrategy:
    """Determine which sync strategy to use for the given path_spec.

    Rules (checked in order):
    - ``user@host:/path`` or ``host:/path``  → SSH_RSYNC
    - ``git+ssh://…``, ``https://…``, ``git@…``, ``*.git`` → GIT_CLONE
    - Anything else (local absolute / relative path) → LOCAL

    Args:
        path_spec: Remote path, git URL, or local filesystem path.

    Returns:
        Appropriate SyncStrategy.
    """
    if _GIT_PATTERN.match(path_spec):
        return SyncStrategy.GIT_CLONE
    if _SSH_PATTERN.match(path_spec):
        return SyncStrategy.SSH_RSYNC
    return SyncStrategy.LOCAL


def sync_codebase(path_spec: str, cache_dir: Path) -> Path:
    """Synchronise a remote codebase into a local cache directory.

    Computes a deterministic slug from *path_spec* and dispatches to
    ``_sync_rsync``, ``_sync_git``, or returns ``Path(path_spec)`` for LOCAL.

    Args:
        path_spec: Remote spec (SSH path, git URL, or local path).
        cache_dir: Parent directory for cached codebases.

    Returns:
        Absolute path to the synchronised local directory.
    """
    strategy = detect_strategy(path_spec)
    slug = _make_slug(path_spec)
    local = (cache_dir / slug).resolve()
    local.mkdir(parents=True, exist_ok=True)

    if strategy is SyncStrategy.LOCAL:
        return Path(path_spec).resolve()
    if strategy is SyncStrategy.SSH_RSYNC:
        return _sync_rsync(path_spec, local)
    # GIT_CLONE
    return _sync_git(path_spec, local)


def _make_slug(path_spec: str) -> str:
    """Convert an arbitrary path_spec into a safe directory name."""
    return re.sub(r"[^a-zA-Z0-9_.\-]", "_", path_spec)[:80]


def _sync_rsync(remote: str, local: Path) -> Path:
    """Sync a remote directory to *local* using rsync over SSH.

    Creates a lockfile while syncing and writes a timestamp on success.

    Args:
        remote: SSH remote path (``user@host:/path`` or ``host:/path``).
        local: Local destination directory (must exist).

    Returns:
        *local* path after successful sync.

    Raises:
        subprocess.CalledProcessError: if rsync exits non-zero.
    """
    lock = local / _SYNC_LOCK
    lock.touch()
    t0 = time.monotonic()
    logger.info("rsync: %s → %s", remote, local)
    try:
        subprocess.run(
            ["rsync", "-avz", "--delete", remote.rstrip("/") + "/", str(local) + "/"],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        lock.unlink(missing_ok=True)

    elapsed = time.monotonic() - t0
    logger.info("rsync: done in %.1fs", elapsed)
    _write_timestamp(local)
    return local


def _sync_git(repo_url: str, local: Path) -> Path:
    """Clone or pull a git repository into *local*.

    Uses ``--depth=1`` for fresh clones and ``--ff-only`` for pulls.

    Args:
        repo_url: Git repository URL.
        local: Local directory. If ``local/.git`` exists, pulls; otherwise clones.

    Returns:
        *local* path after successful sync.

    Raises:
        subprocess.CalledProcessError: if git exits non-zero.
    """
    has_git = (local / ".git").exists()
    if has_git:
        logger.info("git pull: %s → %s", repo_url, local)
        subprocess.run(
            ["git", "-C", str(local), "pull", "--ff-only"],
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        logger.info("git clone: %s → %s", repo_url, local)
        subprocess.run(
            ["git", "clone", "--depth=1", repo_url, str(local)],
            check=True,
            capture_output=True,
            text=True,
        )

    _write_timestamp(local)
    return local


def _write_timestamp(local: Path) -> None:
    ts_file = local / _SYNC_TIMESTAMP
    ts_file.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")


def get_last_sync_time(local: Path) -> datetime | None:
    """Return the UTC datetime of the last successful sync, or None.

    Args:
        local: Local directory where sync was previously run.

    Returns:
        Timezone-aware datetime, or None if no timestamp file exists.
    """
    ts_file = local / _SYNC_TIMESTAMP
    if not ts_file.exists():
        return None
    try:
        text = ts_file.read_text(encoding="utf-8").strip()
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, OSError) as exc:
        logger.debug("get_last_sync_time: failed to read %s: %s", ts_file, exc)
        return None
