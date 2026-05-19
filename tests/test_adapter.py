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
    def test_posts_to_issues_endpoint(self):
        task = Task(project_id="p1", summary="S")
        urls: list[str] = []

        def fake_urlopen(req):
            urls.append(req.full_url)
            return _mock_response({"id": "t1"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _make_adapter().create_task(task)

        assert urls[0].endswith("/Issues"), f"Expected /Issues endpoint, got: {urls[0]}"

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

        assert "/Issues('task-5')" in urls[0]
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


class TestTaskTemplate:
    """Verify templates/task-default.json supplies typeId through the full pipeline."""

    _TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "task-default.json"

    def test_template_has_task_type(self):
        assert self._TEMPLATE_PATH.exists(), "templates/task-default.json must exist"
        data = json.loads(self._TEMPLATE_PATH.read_text())
        assert "task_type" in data, "template must define task_type for Timetta typeId"
        assert data["task_type"], "task_type must be non-empty"

    def test_template_task_type_maps_to_type_id_in_api_body(self):
        data = json.loads(self._TEMPLATE_PATH.read_text())
        data["project_id"] = "proj-1"
        data["summary"] = "Test"
        task = Task.from_dict(data)
        body = task.to_api_body()
        assert "typeId" in body, "typeId must appear in the API request body"
        assert body["typeId"] == data["task_type"]

    def test_e2e_template_to_http_request(self):
        """E2E: read template → fill fields → real adapter → typeId in HTTP POST body."""
        template = json.loads(self._TEMPLATE_PATH.read_text())
        template["project_id"] = "proj-e2e"
        template["summary"] = "Убрать дублирование регионов"
        template["description"] = "Полный текст задачи от пользователя."
        task = Task.from_dict(template)

        http_bodies: list[dict] = []

        def fake_urlopen(req):
            if req.data:
                http_bodies.append(json.loads(req.data))
            return _mock_response({"id": "issue-e2e"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = _make_adapter().create_task(task)

        assert result["id"] == "issue-e2e"
        assert len(http_bodies) == 1
        assert http_bodies[0].get("typeId") == template["task_type"], (
            "typeId from template must appear in the HTTP POST body"
        )
        assert http_bodies[0].get("projectId") == "proj-e2e"
        assert http_bodies[0].get("name") == "Убрать дублирование регионов"


class TestCreateEndpointSmoke:
    """Smoke test: the real TimettaAdapter must POST to /Issues, not /ProjectTasks."""

    def test_real_adapter_posts_to_issues_not_project_tasks(self):
        task = Task(project_id="smoke-proj", summary="Test")
        urls: list[str] = []

        def fake_urlopen(req):
            urls.append(req.full_url)
            return _mock_response({"id": "new-issue-id"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = _make_adapter().create_task(task)

        assert "/Issues" in urls[0], f"Expected /Issues in URL, got: {urls[0]}"
        assert "/ProjectTasks" not in urls[0], "Must not use /ProjectTasks for issue creation"
        assert result["id"] == "new-issue-id"


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


class TestGetUsers:
    def test_returns_list(self):
        payload = {"value": [{"id": "u1", "displayName": "Alice"}, {"id": "u2", "displayName": "Bob"}]}
        with patch("urllib.request.urlopen", return_value=_mock_response(payload)):
            result = _make_adapter().get_users()
        assert result == payload["value"]

    def test_unwraps_odata_value(self):
        payload = {"value": [{"id": "u1", "displayName": "Alice"}], "@odata.count": 1}
        with patch("urllib.request.urlopen", return_value=_mock_response(payload)):
            result = _make_adapter().get_users()
        assert len(result) == 1
        assert result[0]["id"] == "u1"

    def test_bearer_token_sent(self):
        payload = {"value": []}
        captured: list = []

        def fake_urlopen(req):
            captured.append(req)
            return _mock_response(payload)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _make_adapter().get_users()

        assert _has_bearer(captured[0])


class TestGetTags:
    def test_returns_list(self):
        payload = {"value": [{"id": "t1", "name": "backend"}, {"id": "t2", "name": "frontend"}]}
        with patch("urllib.request.urlopen", return_value=_mock_response(payload)):
            result = _make_adapter().get_tags()
        assert result == payload["value"]

    def test_404_returns_empty_list(self):
        err = urllib.error.HTTPError(
            url="http://x", code=404, msg="Not Found", hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(b'{"error":"not found"}'),
        )
        with patch("urllib.request.urlopen", side_effect=err):
            result = _make_adapter().get_tags()
        assert result == []

    def test_other_errors_propagate(self):
        err = urllib.error.HTTPError(
            url="http://x", code=500, msg="Server Error", hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(b'{"error":"server error"}'),
        )
        with patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(RuntimeError, match="500"):
                _make_adapter().get_tags()


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

        assert "/Issues('task-5')/Attachments" in urls[0]
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
