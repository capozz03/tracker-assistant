from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tracker_assistant.timetta.models import Task
from tracker_assistant.timetta.service import create_task, list_projects


def _make_adapter(**overrides) -> MagicMock:
    adapter = MagicMock()
    adapter.get_projects.return_value = overrides.get("projects", [])
    adapter.create_task.return_value = overrides.get("create_result", {"id": "task-1"})
    adapter.add_comment.return_value = {"id": "c1"}
    adapter.attach_file.return_value = {"id": "a1"}
    return adapter


class TestListProjects:
    def test_calls_adapter_get_projects(self):
        projects = [{"id": "1", "name": "Alpha"}]
        adapter = _make_adapter(projects=projects)
        result = list_projects(adapter)
        adapter.get_projects.assert_called_once()
        assert result == projects

    def test_returns_empty_list(self):
        adapter = _make_adapter(projects=[])
        assert list_projects(adapter) == []


class TestCreateTask:
    def test_calls_create_task(self):
        task = Task(project_id="p1", summary="Simple task")
        adapter = _make_adapter()
        result = create_task(adapter, task)
        adapter.create_task.assert_called_once_with(task)
        assert result == {"id": "task-1"}

    def test_no_comments_no_add_comment_calls(self):
        task = Task(project_id="p1", summary="S")
        adapter = _make_adapter()
        create_task(adapter, task)
        adapter.add_comment.assert_not_called()

    def test_no_attachments_no_attach_file_calls(self):
        task = Task(project_id="p1", summary="S")
        adapter = _make_adapter()
        create_task(adapter, task)
        adapter.attach_file.assert_not_called()

    def test_adds_each_comment(self):
        task = Task(project_id="p1", summary="S", comments=["first", "second", "third"])
        adapter = _make_adapter()
        create_task(adapter, task)
        assert adapter.add_comment.call_count == 3
        adapter.add_comment.assert_any_call("task-1", "first")
        adapter.add_comment.assert_any_call("task-1", "second")
        adapter.add_comment.assert_any_call("task-1", "third")

    def test_attaches_each_file(self, tmp_path):
        file1 = tmp_path / "a.txt"
        file2 = tmp_path / "b.txt"
        file1.write_text("a")
        file2.write_text("b")
        task = Task(project_id="p1", summary="S", attachments=[str(file1), str(file2)])
        adapter = _make_adapter()
        create_task(adapter, task, root=tmp_path)
        assert adapter.attach_file.call_count == 2

    def test_attach_resolves_relative_paths(self, tmp_path):
        rel = "docs/readme.txt"
        (tmp_path / "docs").mkdir()
        (tmp_path / rel).write_text("content")
        task = Task(project_id="p1", summary="S", attachments=[rel])
        adapter = _make_adapter()
        create_task(adapter, task, root=tmp_path)
        called_path = adapter.attach_file.call_args[0][1]
        assert called_path == str((tmp_path / rel).resolve())

    def test_returns_create_task_result(self):
        task = Task(project_id="p1", summary="S")
        adapter = _make_adapter(create_result={"id": "task-99", "status": "open"})
        result = create_task(adapter, task)
        assert result["id"] == "task-99"
