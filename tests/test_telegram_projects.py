from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tracker_assistant.telegram.config import ProjectConfig
from tracker_assistant.telegram.projects import ProjectRegistry


def _make_project(project_id: str = "p-default") -> ProjectConfig:
    return ProjectConfig(project_id=project_id)


class TestGetProjectByChatId:
    """Registry has chat_123 → get_project(123) returns that project."""

    def test_returns_per_chat_project_by_int_id(self):
        project = _make_project("p-chat")
        registry = ProjectRegistry({"chat_123": project})

        result = registry.get_project(123)

        assert result is project

    def test_returns_per_chat_project_by_string_id(self):
        project = _make_project("p-chat")
        registry = ProjectRegistry({"chat_456": project})

        result = registry.get_project("456")

        assert result is project

    def test_returned_project_has_correct_project_id(self):
        registry = ProjectRegistry({
            "chat_789": ProjectConfig(project_id="my-project-id"),
        })

        result = registry.get_project(789)

        assert result.project_id == "my-project-id"

    def test_per_chat_entry_takes_priority_over_default(self):
        chat_project = _make_project("p-specific")
        default_project = _make_project("p-default")
        registry = ProjectRegistry({
            "chat_10": chat_project,
            "default": default_project,
        })

        result = registry.get_project(10)

        assert result is chat_project


class TestGetProjectFallbackDefault:
    """Registry has default, get_project(999) → returns default."""

    def test_returns_default_when_no_per_chat_entry(self):
        default_project = _make_project("p-default")
        registry = ProjectRegistry({"default": default_project})

        result = registry.get_project(999)

        assert result is default_project

    def test_returns_default_for_unknown_int_chat_id(self):
        default_project = _make_project("p-fallback")
        registry = ProjectRegistry({
            "chat_1": _make_project("p-other"),
            "default": default_project,
        })

        result = registry.get_project(99999)

        assert result is default_project

    def test_raises_key_error_when_no_chat_and_no_default(self):
        registry = ProjectRegistry({"chat_1": _make_project("p-1")})

        with pytest.raises(KeyError):
            registry.get_project(999)

    def test_default_project_id_is_accessible(self):
        registry = ProjectRegistry({
            "default": ProjectConfig(project_id="default-proj"),
        })

        result = registry.get_project(0)

        assert result.project_id == "default-proj"


class TestListProjects:
    """list_projects returns all (key, ProjectConfig) tuples."""

    def test_returns_all_entries_as_tuples(self):
        p1 = _make_project("p-1")
        p2 = _make_project("p-2")
        registry = ProjectRegistry({"chat_1": p1, "default": p2})

        result = registry.list_projects()

        assert len(result) == 2

    def test_each_entry_is_key_config_tuple(self):
        project = _make_project("p-1")
        registry = ProjectRegistry({"chat_42": project})

        result = registry.list_projects()

        key, cfg = result[0]
        assert key == "chat_42"
        assert cfg is project

    def test_returns_empty_list_for_empty_registry(self):
        registry = ProjectRegistry({})

        result = registry.list_projects()

        assert result == []

    def test_preserves_insertion_order(self):
        p1 = _make_project("p-alpha")
        p2 = _make_project("p-beta")
        p3 = _make_project("p-gamma")
        registry = ProjectRegistry({"a": p1, "b": p2, "c": p3})

        result = registry.list_projects()

        keys = [k for k, _ in result]
        assert keys == ["a", "b", "c"]

    def test_all_project_configs_accessible(self):
        projects = {
            "chat_1": ProjectConfig(project_id="id-1", sprint_id="s-1"),
            "chat_2": ProjectConfig(project_id="id-2"),
            "default": ProjectConfig(project_id="id-default"),
        }
        registry = ProjectRegistry(projects)

        result = registry.list_projects()

        result_dict = dict(result)
        assert result_dict["chat_1"].project_id == "id-1"
        assert result_dict["chat_1"].sprint_id == "s-1"
        assert result_dict["default"].project_id == "id-default"
