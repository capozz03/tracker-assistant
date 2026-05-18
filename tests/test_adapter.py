from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tracker_assistant.adapters.yandex_tracker_adapter import YandexTrackerAdapter
from tracker_assistant.models import Task


def _make_adapter() -> YandexTrackerAdapter:
    return YandexTrackerAdapter(token="test-token", org_id="test-org", org_type="cloud")


def _mock_response(payload) -> MagicMock:
    body = json.dumps(payload).encode()
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = body
    return mock


class TestGetProjects:
    def test_returns_list_single_page(self):
        projects = [{"id": "1", "name": "Alpha"}, {"id": "2", "name": "Beta"}]
        with patch("urllib.request.urlopen", return_value=_mock_response(projects)) as m:
            result = _make_adapter().get_projects()
        assert result == projects
        assert m.call_count == 1

    def test_paginates_until_short_batch(self):
        page1 = [{"id": str(i)} for i in range(50)]
        page2 = [{"id": "51"}]
        responses = [_mock_response(page1), _mock_response(page2)]
        with patch("urllib.request.urlopen", side_effect=responses):
            result = _make_adapter().get_projects()
        assert len(result) == 51

    def test_empty_response_stops_pagination(self):
        with patch("urllib.request.urlopen", return_value=_mock_response([])):
            result = _make_adapter().get_projects()
        assert result == []


class TestCreateIssue:
    def test_builds_minimal_body(self):
        task = Task(queue="MYQUEUE", summary="Test task")
        captured: list[dict] = []

        def fake_urlopen(req):
            captured.append(json.loads(req.data))
            return _mock_response({"key": "MYQUEUE-1"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = _make_adapter().create_issue(task)

        assert result["key"] == "MYQUEUE-1"
        body = captured[0]
        assert body["queue"] == "MYQUEUE"
        assert body["summary"] == "Test task"
        assert body["type"] == "task"
        assert "description" not in body
        assert "project" not in body

    def test_includes_tags_and_assignee(self):
        task = Task(
            queue="Q",
            summary="S",
            tags=["tag1", "tag2"],
            assignee="user123",
            followers=["obs1"],
        )
        captured: list[dict] = []

        def fake_urlopen(req):
            captured.append(json.loads(req.data))
            return _mock_response({"key": "Q-1"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _make_adapter().create_issue(task)

        body = captured[0]
        assert body["tags"] == ["tag1", "tag2"]
        assert body["assignee"] == "user123"
        assert body["followers"] == ["obs1"]

    def test_extra_fields_merged_into_body(self):
        task = Task(queue="Q", summary="S", extra={"priority": "critical", "sprint": "2024-1"})
        captured: list[dict] = []

        def fake_urlopen(req):
            captured.append(json.loads(req.data))
            return _mock_response({"key": "Q-1"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _make_adapter().create_issue(task)

        body = captured[0]
        assert body["priority"] == "critical"
        assert body["sprint"] == "2024-1"

    def test_project_id_included_when_set(self):
        task = Task(queue="Q", summary="S", project_id="42")
        captured: list[dict] = []

        def fake_urlopen(req):
            captured.append(json.loads(req.data))
            return _mock_response({"key": "Q-1"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _make_adapter().create_issue(task)

        assert captured[0]["project"] == {"primary": 42}


class TestAddComment:
    def test_posts_to_correct_url(self):
        urls: list[str] = []

        def fake_urlopen(req):
            urls.append(req.full_url)
            return _mock_response({"id": "c1"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = _make_adapter().add_comment("PROJ-10", "Hello!")

        assert "/issues/PROJ-10/comments" in urls[0]
        assert result["id"] == "c1"


class TestHTTPError:
    def test_raises_runtime_error_on_http_error(self):
        err = urllib.error.HTTPError(
            url="http://x", code=422, msg="Unprocessable", hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(b'{"error":"bad"}'),
        )
        with patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(RuntimeError, match="422"):
                _make_adapter().get_projects()


class TestAttachFile:
    def test_sends_multipart_request(self, tmp_path):
        dummy = tmp_path / "doc.pdf"
        dummy.write_bytes(b"%PDF-1.4 content")

        urls: list[str] = []
        content_types: list[str] = []

        def fake_urlopen(req):
            urls.append(req.full_url)
            content_types.append(req.get_header("Content-type"))
            return _mock_response({"id": "att1"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = _make_adapter().attach_file("PROJ-5", str(dummy))

        assert "/issues/PROJ-5/attachments" in urls[0]
        assert "multipart/form-data" in content_types[0]
        assert result["id"] == "att1"
