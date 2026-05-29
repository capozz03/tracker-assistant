"""Tests for submit module: stack scanner, prompt utils, claude client."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tracker_assistant.submit.stack_detector import scan_project_stack
from tracker_assistant.submit.prompt import resolve_tags
from tracker_assistant.submit.service import (
    DEFAULT_TASK_TYPE,
    create_tasks,
    generate_tasks,
    submit_requirements,
)
from tracker_assistant.shared.claude_client import call_claude_list


# ---------------------------------------------------------------------------
# scan_project_stack
# ---------------------------------------------------------------------------

class TestScanProjectStack:
    def test_nonexistent_path_returns_empty(self, tmp_path):
        result = scan_project_stack(tmp_path / "does_not_exist")
        assert result["has_frontend"] is False
        assert result["has_backend"] is False
        assert result["technologies"] == []

    def test_detects_frontend_from_tsx_files(self, tmp_path):
        (tmp_path / "App.tsx").write_text("export default function App() {}")
        result = scan_project_stack(tmp_path)
        assert result["has_frontend"] is True

    def test_detects_backend_from_py_files(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hello')")
        result = scan_project_stack(tmp_path)
        assert result["has_backend"] is True

    def test_detects_from_package_json_react(self, tmp_path):
        (tmp_path / "package.json").write_text(
            json.dumps({"dependencies": {"react": "^18.0.0"}})
        )
        result = scan_project_stack(tmp_path)
        assert result["has_frontend"] is True
        assert "React" in result["technologies"]

    def test_detects_from_package_json_express(self, tmp_path):
        (tmp_path / "package.json").write_text(
            json.dumps({"dependencies": {"express": "^4.18.0"}})
        )
        result = scan_project_stack(tmp_path)
        assert result["has_backend"] is True
        assert "Express" in result["technologies"]

    def test_detects_from_next_config(self, tmp_path):
        (tmp_path / "next.config.js").write_text("module.exports = {}")
        result = scan_project_stack(tmp_path)
        assert result["has_frontend"] is True
        assert "Next.js" in result["technologies"]

    def test_detects_frontend_dir_hint(self, tmp_path):
        (tmp_path / "frontend").mkdir()
        result = scan_project_stack(tmp_path)
        assert result["has_frontend"] is True

    def test_detects_backend_dir_hint(self, tmp_path):
        (tmp_path / "api").mkdir()
        result = scan_project_stack(tmp_path)
        assert result["has_backend"] is True

    def test_reads_readme(self, tmp_path):
        (tmp_path / "README.md").write_text("# My App\nA cool project.")
        result = scan_project_stack(tmp_path)
        assert "My App" in result["description"]

    def test_skips_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "some_lib"
        nm.mkdir(parents=True)
        (nm / "index.tsx").write_text("export {}")
        result = scan_project_stack(tmp_path)
        # node_modules should be skipped — no frontend detected from it alone
        assert result["has_frontend"] is False

    def test_fullstack_detected(self, tmp_path):
        (tmp_path / "frontend").mkdir()
        (tmp_path / "backend").mkdir()
        result = scan_project_stack(tmp_path)
        assert result["has_frontend"] is True
        assert result["has_backend"] is True


# ---------------------------------------------------------------------------
# _call_claude (submit_task version — returns list)
# ---------------------------------------------------------------------------

class TestSubmitTaskCallClaude:
    """submit_task._call_claude must return a list and handle text preambles."""

    def _run(self, stdout: str) -> list:
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = stdout
        mock.stderr = ""
        with patch("subprocess.run", return_value=mock):
            return call_claude_list("prompt")

    def test_plain_json_array(self):
        result = self._run('[{"project_id": "p1", "summary": "S"}]')
        assert isinstance(result, list)
        assert result[0]["summary"] == "S"

    def test_json_in_code_fence(self):
        payload = '[{"project_id": "p1", "summary": "fenced"}]'
        result = self._run(f"```json\n{payload}\n```")
        assert result[0]["summary"] == "fenced"

    def test_json_with_text_preamble(self):
        """Claude sometimes writes text before the JSON array."""
        payload = '[{"project_id": "p1", "summary": "after preamble"}]'
        result = self._run(f"Вот задачи:\n\n```json\n{payload}\n```")
        assert result[0]["summary"] == "after preamble"

    def test_single_dict_wrapped_in_list(self):
        """If Claude returns an object instead of array, wrap it."""
        result = self._run('{"project_id": "p1", "summary": "single"}')
        assert isinstance(result, list)
        assert len(result) == 1

    def test_raises_on_invalid_json(self):
        with pytest.raises(RuntimeError, match="невалидный JSON"):
            self._run("not json at all")

    def test_raises_on_nonzero_exit(self):
        mock = MagicMock()
        mock.returncode = 1
        mock.stdout = ""
        mock.stderr = "claude crashed"
        with patch("subprocess.run", return_value=mock):
            with pytest.raises(RuntimeError, match="claude -p"):
                call_claude_list("prompt")


# ---------------------------------------------------------------------------
# _resolve_tags
# ---------------------------------------------------------------------------

_KNOWN_TAGS = [
    {"id": "aaa-111", "name": "Фронтенд", "code": "FE"},
    {"id": "bbb-222", "name": "Бекенд",   "code": "BE"},
    {"id": "ccc-333", "name": "Эпик",     "code": "EP"},
    {"id": "ddd-444", "name": "Правки",   "code": ""},
]


class TestResolveTagsFunction:
    def test_uuid_passthrough(self):
        result = resolve_tags(["aaa-111", "bbb-222"], _KNOWN_TAGS)
        assert result == ["aaa-111", "bbb-222"]

    def test_name_to_uuid_exact(self):
        result = resolve_tags(["Фронтенд"], _KNOWN_TAGS)
        assert result == ["aaa-111"]

    def test_name_case_insensitive(self):
        result = resolve_tags(["фронтенд", "БЕКЕНД"], _KNOWN_TAGS)
        assert result == ["aaa-111", "bbb-222"]

    def test_english_name_not_resolved(self):
        """English names like 'frontend' don't match Russian 'Фронтенд'."""
        result = resolve_tags(["frontend"], _KNOWN_TAGS)
        assert result == []

    def test_code_to_uuid(self):
        result = resolve_tags(["FE"], _KNOWN_TAGS)
        assert result == ["aaa-111"]

    def test_code_case_insensitive(self):
        result = resolve_tags(["be"], _KNOWN_TAGS)
        assert result == ["bbb-222"]

    def test_unknown_tag_skipped(self):
        result = resolve_tags(["unknown-xyz"], _KNOWN_TAGS)
        assert result == []

    def test_mixed_input(self):
        result = resolve_tags(["aaa-111", "Бекенд", "EP", "garbage"], _KNOWN_TAGS)
        assert result == ["aaa-111", "bbb-222", "ccc-333"]

    def test_empty_input(self):
        result = resolve_tags([], _KNOWN_TAGS)
        assert result == []

    def test_empty_known_tags(self):
        result = resolve_tags(["aaa-111"], [])
        assert result == []

    def test_empty_code_ignored_for_code_lookup(self):
        """Tag with empty code should not be matched by empty string."""
        result = resolve_tags([""], _KNOWN_TAGS)
        assert result == []


# ---------------------------------------------------------------------------
# generate_tasks / create_tasks split
# ---------------------------------------------------------------------------


class TestGenerateTasks:
    def _claude_tasks(self):
        return [
            {"summary": "A", "description": "d", "tags": ["aaa-111"], "assignee": "u1"},
            {"summary": "B", "tags": [], "assignee": "", "project_id": "explicit"},
        ]

    def test_generate_tasks_no_timetta_calls(self, tmp_path):
        """generate_tasks must only call Claude and normalize — never touch Timetta."""
        with patch(
            "tracker_assistant.submit.service.call_claude_list",
            return_value=self._claude_tasks(),
        ) as mock_claude:
            result = generate_tasks(
                "requirements",
                "proj-uuid",
                None,  # no project_path → empty stack, no scanning
                tmp_path,
                tags=[],
                users=[],
                sprint_id="sprint-1",
            )

        mock_claude.assert_called_once()
        assert len(result) == 2
        # project_id defaulted where missing, kept where explicit
        assert result[0]["project_id"] == "proj-uuid"
        assert result[1]["project_id"] == "explicit"
        # task_type defaulted
        assert result[0]["task_type"] == DEFAULT_TASK_TYPE
        # sprint id injected into extra
        assert result[0]["extra"]["sprintId"] == "sprint-1"
        # raw tags/assignee preserved inside dicts for preview + creation
        assert result[0]["tags"] == ["aaa-111"]
        assert result[0]["assignee"] == "u1"


class TestCreateTasks:
    def test_create_tasks_creates_and_returns_urls(self, tmp_path):
        adapter = MagicMock()
        task_dicts = [
            {"project_id": "p", "summary": "A", "task_type": "tt", "tags": ["aaa-111"], "assignee": "u1"},
            {"project_id": "p", "summary": "B", "task_type": "tt", "tags": [], "assignee": ""},
        ]
        known_tags = [{"id": "aaa-111", "name": "Фронтенд"}]
        created_ids = iter(["id-1", "id-2"])

        with patch(
            "tracker_assistant.submit.service.create_task",
            side_effect=lambda a, t, root=None: {"id": next(created_ids)},
        ) as mock_create:
            results = create_tasks(task_dicts, adapter=adapter, tags=known_tags, root=tmp_path)

        assert mock_create.call_count == 2
        assert [r["id"] for r in results] == ["id-1", "id-2"]
        assert results[0]["url"] == "https://app.timetta.com/issues/id-1"
        assert results[0]["tags"] == ["aaa-111"]  # resolved name→uuid passthrough
        # first task carried tags + assignee → a follow-up update_task is issued
        adapter.update_task.assert_any_call("id-1", tags=["aaa-111"], assigneeId="u1")
        # input dicts must NOT be mutated — preview/pending state still holds them
        assert task_dicts[0]["tags"] == ["aaa-111"]


class TestSubmitRequirementsWrapper:
    def test_submit_requirements_wrapper(self, tmp_path):
        """The wrapper == generate_tasks + create_tasks (back-compat for the CLI)."""
        adapter = MagicMock()
        known_tags = [{"id": "aaa-111", "name": "Фронтенд"}]

        with patch(
            "tracker_assistant.submit.service.call_claude_list",
            return_value=[{"summary": "A", "tags": ["aaa-111"], "assignee": "u1"}],
        ), patch(
            "tracker_assistant.submit.service.create_task",
            return_value={"id": "id-1"},
        ) as mock_create:
            results = submit_requirements(
                requirements="req",
                project_id="proj-uuid",
                adapter=adapter,
                users=[],
                tags=known_tags,
                project_path=None,
                root=tmp_path,
                sprint_id="",
            )

        mock_create.assert_called_once()
        assert results[0]["id"] == "id-1"
        assert results[0]["url"] == "https://app.timetta.com/issues/id-1"
        assert results[0]["summary"] == "A"
        assert results[0]["tags"] == ["aaa-111"]
