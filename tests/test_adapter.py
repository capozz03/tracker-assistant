from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tracker_assistant.adapters.timetta_adapter import TimettaAdapter
from tracker_assistant.models import Task


def _make_adapter() -> TimettaAdapter:
    return TimettaAdapter(token="test-bearer-token")


def _mock_response(payload) -> MagicMock:
    body = json.dumps(payload).encode()
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = body
    return mock


def _has_bearer(req) -> bool:
    return req.get_header("Authorization") == "Bearer test-bearer-token"


class TestGetProjects:
    def test_returns_list_single_page(self):
        payload = {"value": [{"id": "1", "name": "Alpha"}, {"id": "2", "name": "Beta"}]}
        with patch("urllib.request.urlopen", return_value=_mock_response(payload)) as m:
            result = _make_adapter().get_projects()
        assert result == payload["value"]
        assert m.call_count == 1

    def test_bearer_token_sent(self):
        payload = {"value": [{"id": "1"}]}
        captured: list = []

        def fake_urlopen(req):
            captured.append(req)
            return _mock_response(payload)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _make_adapter().get_projects()

        assert _has_bearer(captured[0])

    def test_empty_value_returns_empty_list(self):
        with patch("urllib.request.urlopen", return_value=_mock_response({"value": []})):
            result = _make_adapter().get_projects()
        assert result == []


class TestCreateTask:
    def test_builds_minimal_body(self):
        task = Task(project_id="proj-1", summary="Test task")
        captured: list[dict] = []

        def fake_urlopen(req):
            captured.append(json.loads(req.data))
            return _mock_response({"id": "task-42", "name": "Test task"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = _make_adapter().create_task(task)

        assert result["id"] == "task-42"
        body = captured[0]
        assert body["projectId"] == "proj-1"
        assert body["name"] == "Test task"
        assert "description" not in body

    def test_includes_assignee_and_tags(self):
        task = Task(
            project_id="p1",
            summary="S",
            assignee="user-abc",
            tags=["backend", "api"],
        )
        captured: list[dict] = []

        def fake_urlopen(req):
            captured.append(json.loads(req.data))
            return _mock_response({"id": "t1"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _make_adapter().create_task(task)

        body = captured[0]
        assert body["assigneeId"] == "user-abc"
        assert body["tags"] == ["backend", "api"]

    def test_extra_fields_merged_into_body(self):
        task = Task(project_id="p1", summary="S", extra={"priority": 2, "sprint": "2024-Q1"})
        captured: list[dict] = []

        def fake_urlopen(req):
            captured.append(json.loads(req.data))
            return _mock_response({"id": "t1"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _make_adapter().create_task(task)

        body = captured[0]
        assert body["priority"] == 2
        assert body["sprint"] == "2024-Q1"

    def test_bearer_token_sent(self):
        task = Task(project_id="p1", summary="S")
        captured: list = []

        def fake_urlopen(req):
            captured.append(req)
            return _mock_response({"id": "t1"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _make_adapter().create_task(task)

        assert _has_bearer(captured[0])


class TestGetTask:
    def test_gets_correct_url(self):
        urls: list[str] = []

        def fake_urlopen(req):
            urls.append(req.full_url)
            return _mock_response({"id": "task-5"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = _make_adapter().get_task("task-5")

        assert "/ProjectTasks('task-5')" in urls[0]
        assert result["id"] == "task-5"


class TestUpdateTask:
    def test_sends_patch_with_fields(self):
        methods: list[str] = []
        bodies: list[dict] = []

        def fake_urlopen(req):
            methods.append(req.get_method())
            bodies.append(json.loads(req.data))
            return _mock_response({"id": "task-5"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _make_adapter().update_task("task-5", name="New name", priority=3)

        assert methods[0] == "PATCH"
        assert bodies[0]["name"] == "New name"
        assert bodies[0]["priority"] == 3


class TestHTTPError:
    def test_raises_runtime_error_on_http_error(self):
        err = urllib.error.HTTPError(
            url="http://x", code=401, msg="Unauthorized", hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(b'{"error":"unauthorized"}'),
        )
        with patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(RuntimeError, match="401"):
                _make_adapter().get_projects()


class TestAddCommentGraceful:
    def test_returns_none_on_404(self):
        err = urllib.error.HTTPError(
            url="http://x", code=404, msg="Not Found", hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(b'{"error":"not found"}'),
        )
        with patch("urllib.request.urlopen", side_effect=err):
            result = _make_adapter().add_comment("task-1", "Hello!")

        assert result is None


class TestAttachFile:
    def test_sends_multipart_request(self, tmp_path):
        dummy = tmp_path / "doc.pdf"
        dummy.write_bytes(b"%PDF-1.4 content")

        urls: list[str] = []
        content_types: list[str] = []

        def fake_urlopen(req):
            urls.append(req.full_url)
            content_types.append(req.get_header("Content-type"))
            return _mock_response({"id": "att-1"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = _make_adapter().attach_file("task-5", str(dummy))

        assert "/ProjectTasks('task-5')/Attachments" in urls[0]
        assert "multipart/form-data" in content_types[0]
        assert result["id"] == "att-1"

    def test_returns_none_on_404(self, tmp_path):
        dummy = tmp_path / "doc.pdf"
        dummy.write_bytes(b"content")
        err = urllib.error.HTTPError(
            url="http://x", code=404, msg="Not Found", hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(b'{"error":"not found"}'),
        )
        with patch("urllib.request.urlopen", side_effect=err):
            result = _make_adapter().attach_file("task-1", str(dummy))

        assert result is None
