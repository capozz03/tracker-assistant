"""Tests for get_tags DirectoryEntries endpoint and _call_claude code-fence stripping."""
from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tracker_assistant.timetta.adapter import TimettaAdapter
from tracker_assistant.shared.claude_client import call_claude


def _make_adapter() -> TimettaAdapter:
    return TimettaAdapter(token="test-token")


def _mock_response(payload) -> MagicMock:
    body = json.dumps(payload).encode()
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = body
    return mock


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url="", code=code, msg="", hdrs=MagicMock(), fp=io.BytesIO(b""))


# ---------------------------------------------------------------------------
# get_tags — DirectoryEntries endpoint
# ---------------------------------------------------------------------------

class TestGetTagsDirectoryEntries:
    def test_returns_tags_from_directory_entries(self):
        payload = {"value": [{"id": "uuid1", "name": "backend"}, {"id": "uuid2", "name": "frontend"}]}
        with patch("urllib.request.urlopen", return_value=_mock_response(payload)):
            result = _make_adapter().get_tags()
        assert result == payload["value"]

    def test_uses_default_directory_id(self):
        captured: list[str] = []

        def side_effect(req):
            captured.append(req.full_url)
            return _mock_response({"value": []})

        with patch("urllib.request.urlopen", side_effect=side_effect):
            _make_adapter().get_tags()

        assert TimettaAdapter.DEFAULT_TAGS_DIR_ID in captured[0]

    def test_custom_directory_id_overrides_default(self):
        custom = "11111111-2222-3333-4444-555555555555"
        captured: list[str] = []

        def side_effect(req):
            captured.append(req.full_url)
            return _mock_response({"value": []})

        with patch("urllib.request.urlopen", side_effect=side_effect):
            TimettaAdapter(token="tok", tags_dir_id=custom).get_tags()

        assert custom in captured[0]
        assert TimettaAdapter.DEFAULT_TAGS_DIR_ID not in captured[0]

    def test_non_404_errors_propagate(self):
        with patch("urllib.request.urlopen", side_effect=_http_error(403)):
            with pytest.raises(RuntimeError, match="403"):
                _make_adapter().get_tags()


# ---------------------------------------------------------------------------
# call_claude — markdown code fence stripping (shared.claude_client)
# ---------------------------------------------------------------------------

class TestCallClaudeStripFences:
    def _run(self, stdout: str):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = stdout
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            return call_claude("test prompt")

    def test_parses_plain_json(self):
        result = self._run('{"summary": "ok", "tags": []}')
        assert result["summary"] == "ok"

    def test_strips_json_fence(self):
        wrapped = '```json\n{"summary": "fenced", "tags": []}\n```'
        result = self._run(wrapped)
        assert result["summary"] == "fenced"

    def test_strips_plain_fence(self):
        wrapped = '```\n{"summary": "plain", "tags": []}\n```'
        result = self._run(wrapped)
        assert result["summary"] == "plain"

    def test_raises_on_invalid_json_after_strip(self):
        wrapped = '```json\nnot valid json\n```'
        with pytest.raises(SystemExit, match="невалидный JSON"):
            self._run(wrapped)

    def test_raises_on_nonzero_exit(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(SystemExit, match="claude -p"):
                call_claude("test prompt")
