from __future__ import annotations

"""Tests for tracker_assistant.telegram.vps_sync."""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tracker_assistant.telegram.vps_sync import (
    SyncStrategy,
    _sync_git,
    _sync_rsync,
    detect_strategy,
    get_last_sync_time,
)


# ---------------------------------------------------------------------------
# detect_strategy
# ---------------------------------------------------------------------------


class TestDetectStrategySshRsync:
    """detect_strategy returns SSH_RSYNC for SSH remote paths."""

    def test_user_at_host_colon_path(self) -> None:
        result = detect_strategy("user@host:/path/to/project")
        assert result is SyncStrategy.SSH_RSYNC

    def test_host_colon_path(self) -> None:
        result = detect_strategy("host:/path/to/project")
        assert result is SyncStrategy.SSH_RSYNC

    def test_host_with_dots_colon_path(self) -> None:
        result = detect_strategy("myhost.example.com:/srv/app")
        assert result is SyncStrategy.SSH_RSYNC


class TestDetectStrategyGitClone:
    """detect_strategy returns GIT_CLONE for git/https URLs."""

    def test_https_github(self) -> None:
        result = detect_strategy("https://github.com/org/repo")
        assert result is SyncStrategy.GIT_CLONE

    def test_git_at_github_ssh(self) -> None:
        result = detect_strategy("git@github.com:org/repo.git")
        assert result is SyncStrategy.GIT_CLONE

    def test_git_plus_ssh_url(self) -> None:
        result = detect_strategy("git+ssh://git@github.com/org/repo")
        assert result is SyncStrategy.GIT_CLONE

    def test_http_url(self) -> None:
        result = detect_strategy("http://example.com/repo.git")
        assert result is SyncStrategy.GIT_CLONE

    def test_dot_git_suffix(self) -> None:
        result = detect_strategy("/some/local/path/repo.git")
        assert result is SyncStrategy.GIT_CLONE


class TestDetectStrategyLocal:
    """detect_strategy returns LOCAL for filesystem paths."""

    def test_absolute_path(self) -> None:
        result = detect_strategy("/absolute/path/to/project")
        assert result is SyncStrategy.LOCAL

    def test_relative_path(self) -> None:
        result = detect_strategy("relative/path")
        assert result is SyncStrategy.LOCAL

    def test_dot_relative_path(self) -> None:
        result = detect_strategy("./relative/path")
        assert result is SyncStrategy.LOCAL


# ---------------------------------------------------------------------------
# _sync_rsync
# ---------------------------------------------------------------------------


class TestSyncRsync:
    """_sync_rsync calls subprocess.run with correct rsync arguments."""

    def test_subprocess_called_with_rsync_args(self, tmp_path: Path) -> None:
        with patch("tracker_assistant.telegram.vps_sync.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = _sync_rsync("user@host:/srv/app", tmp_path)

        assert mock_run.called
        args = mock_run.call_args[0][0]  # first positional arg (the command list)
        assert "rsync" in args
        assert "user@host:/srv/app/" in args
        assert str(tmp_path) + "/" in args

    def test_remote_trailing_slash_normalised(self, tmp_path: Path) -> None:
        """A trailing slash on the remote spec must not produce double slashes."""
        with patch("tracker_assistant.telegram.vps_sync.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            _sync_rsync("user@host:/srv/app/", tmp_path)

        args = mock_run.call_args[0][0]
        # rstrip("/") + "/" should be exactly one slash
        assert "user@host:/srv/app/" in args
        assert "user@host:/srv/app//" not in args

    def test_returns_local_path(self, tmp_path: Path) -> None:
        with patch("tracker_assistant.telegram.vps_sync.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = _sync_rsync("user@host:/srv/app", tmp_path)

        assert result == tmp_path

    def test_delete_flag_present(self, tmp_path: Path) -> None:
        with patch("tracker_assistant.telegram.vps_sync.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            _sync_rsync("user@host:/srv/app", tmp_path)

        args = mock_run.call_args[0][0]
        assert "--delete" in args


# ---------------------------------------------------------------------------
# _sync_git
# ---------------------------------------------------------------------------


class TestSyncGitCloneFresh:
    """_sync_git runs git clone when no .git directory exists."""

    def test_git_clone_called(self, tmp_path: Path) -> None:
        # No .git directory → should clone
        with patch("tracker_assistant.telegram.vps_sync.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = _sync_git("https://github.com/org/repo", tmp_path)

        assert mock_run.called
        args = mock_run.call_args[0][0]
        assert "git" in args
        assert "clone" in args
        assert "--depth=1" in args
        assert "https://github.com/org/repo" in args

    def test_returns_local_path(self, tmp_path: Path) -> None:
        with patch("tracker_assistant.telegram.vps_sync.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = _sync_git("https://github.com/org/repo", tmp_path)

        assert result == tmp_path


class TestSyncGitPullExisting:
    """_sync_git runs git pull when .git directory already exists."""

    def test_git_pull_called(self, tmp_path: Path) -> None:
        # Create a .git directory to simulate an existing clone
        (tmp_path / ".git").mkdir()

        with patch("tracker_assistant.telegram.vps_sync.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = _sync_git("https://github.com/org/repo", tmp_path)

        assert mock_run.called
        args = mock_run.call_args[0][0]
        assert "git" in args
        assert "-C" in args
        assert str(tmp_path) in args
        assert "pull" in args
        assert "--ff-only" in args

    def test_pull_does_not_contain_clone(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()

        with patch("tracker_assistant.telegram.vps_sync.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            _sync_git("https://github.com/org/repo", tmp_path)

        args = mock_run.call_args[0][0]
        assert "clone" not in args

    def test_returns_local_path(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()

        with patch("tracker_assistant.telegram.vps_sync.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = _sync_git("https://github.com/org/repo", tmp_path)

        assert result == tmp_path


# ---------------------------------------------------------------------------
# get_last_sync_time
# ---------------------------------------------------------------------------


class TestGetLastSyncTime:
    """get_last_sync_time returns None or a datetime."""

    def test_no_timestamp_file_returns_none(self, tmp_path: Path) -> None:
        result = get_last_sync_time(tmp_path)
        assert result is None

    def test_returns_datetime_when_file_exists(self, tmp_path: Path) -> None:
        ts = "2026-05-25T12:00:00+00:00"
        (tmp_path / ".sync_timestamp").write_text(ts, encoding="utf-8")

        result = get_last_sync_time(tmp_path)

        assert isinstance(result, datetime)
        assert result.year == 2026
        assert result.month == 5
        assert result.day == 25

    def test_returned_datetime_is_timezone_aware(self, tmp_path: Path) -> None:
        ts = "2026-05-25T12:00:00+00:00"
        (tmp_path / ".sync_timestamp").write_text(ts, encoding="utf-8")

        result = get_last_sync_time(tmp_path)

        assert result is not None
        assert result.tzinfo is not None

    def test_naive_datetime_in_file_gets_utc_tzinfo(self, tmp_path: Path) -> None:
        ts = "2026-05-25T12:00:00"  # no timezone info
        (tmp_path / ".sync_timestamp").write_text(ts, encoding="utf-8")

        result = get_last_sync_time(tmp_path)

        assert result is not None
        assert result.tzinfo == timezone.utc

    def test_corrupt_file_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / ".sync_timestamp").write_text("not-a-datetime", encoding="utf-8")

        result = get_last_sync_time(tmp_path)

        assert result is None
