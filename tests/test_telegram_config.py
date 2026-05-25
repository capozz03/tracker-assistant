from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tracker_assistant.telegram.config import BotConfig, ProjectConfig, load_config


class TestLoadConfigFromEnv:
    """TELEGRAM_TOKEN from env, no telegram_projects.json → default project from TIMETTA_PROJECT_ID."""

    def test_returns_bot_config_with_token(self, tmp_path):
        (tmp_path / ".env").write_text(
            "TELEGRAM_TOKEN=tok-abc\nTIMETTA_PROJECT_ID=proj-001\n",
            encoding="utf-8",
        )

        config = load_config(tmp_path)

        assert isinstance(config, BotConfig)
        assert config.token == "tok-abc"

    def test_creates_default_project_from_timetta_project_id(self, tmp_path):
        (tmp_path / ".env").write_text(
            "TELEGRAM_TOKEN=tok-abc\nTIMETTA_PROJECT_ID=proj-001\n",
            encoding="utf-8",
        )

        config = load_config(tmp_path)

        assert "default" in config.projects
        assert config.projects["default"].project_id == "proj-001"

    def test_default_project_empty_when_timetta_project_id_absent(self, tmp_path):
        (tmp_path / ".env").write_text(
            "TELEGRAM_TOKEN=tok-abc\n",
            encoding="utf-8",
        )

        config = load_config(tmp_path)

        assert "default" in config.projects
        assert config.projects["default"].project_id == ""

    def test_root_set_on_config(self, tmp_path):
        (tmp_path / ".env").write_text("TELEGRAM_TOKEN=tok-abc\n", encoding="utf-8")

        config = load_config(tmp_path)

        assert config.root == tmp_path

    def test_env_var_overrides_dot_env(self, tmp_path, monkeypatch):
        (tmp_path / ".env").write_text(
            "TELEGRAM_TOKEN=from-file\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("TELEGRAM_TOKEN", "from-env")

        config = load_config(tmp_path)

        assert config.token == "from-env"


class TestLoadConfigWithProjectsJson:
    """telegram_projects.json present → loads correct ProjectConfig objects."""

    def test_loads_project_ids(self, tmp_path):
        (tmp_path / ".env").write_text("TELEGRAM_TOKEN=tok-abc\n", encoding="utf-8")
        projects_data = {
            "alpha": {"project_id": "p-alpha", "sprint_id": "s-001"},
            "beta": {"project_id": "p-beta"},
        }
        (tmp_path / "telegram_projects.json").write_text(
            json.dumps(projects_data), encoding="utf-8"
        )

        config = load_config(tmp_path)

        assert "alpha" in config.projects
        assert config.projects["alpha"].project_id == "p-alpha"
        assert config.projects["beta"].project_id == "p-beta"

    def test_loads_sprint_id(self, tmp_path):
        (tmp_path / ".env").write_text("TELEGRAM_TOKEN=tok-abc\n", encoding="utf-8")
        (tmp_path / "telegram_projects.json").write_text(
            json.dumps({"main": {"project_id": "p-1", "sprint_id": "sprint-42"}}),
            encoding="utf-8",
        )

        config = load_config(tmp_path)

        assert config.projects["main"].sprint_id == "sprint-42"

    def test_loads_project_path(self, tmp_path):
        (tmp_path / ".env").write_text("TELEGRAM_TOKEN=tok-abc\n", encoding="utf-8")
        (tmp_path / "telegram_projects.json").write_text(
            json.dumps({"main": {"project_id": "p-1", "project_path": "/some/path"}}),
            encoding="utf-8",
        )

        config = load_config(tmp_path)

        assert config.projects["main"].project_path == Path("/some/path")

    def test_project_path_none_when_absent(self, tmp_path):
        (tmp_path / ".env").write_text("TELEGRAM_TOKEN=tok-abc\n", encoding="utf-8")
        (tmp_path / "telegram_projects.json").write_text(
            json.dumps({"main": {"project_id": "p-1"}}),
            encoding="utf-8",
        )

        config = load_config(tmp_path)

        assert config.projects["main"].project_path is None

    def test_loads_vps_remote(self, tmp_path):
        (tmp_path / ".env").write_text("TELEGRAM_TOKEN=tok-abc\n", encoding="utf-8")
        (tmp_path / "telegram_projects.json").write_text(
            json.dumps({"main": {"project_id": "p-1", "vps_remote": "user@host:/path"}}),
            encoding="utf-8",
        )

        config = load_config(tmp_path)

        assert config.projects["main"].vps_remote == "user@host:/path"

    def test_returns_project_config_instances(self, tmp_path):
        (tmp_path / ".env").write_text("TELEGRAM_TOKEN=tok-abc\n", encoding="utf-8")
        (tmp_path / "telegram_projects.json").write_text(
            json.dumps({"chat_123": {"project_id": "p-chat"}}),
            encoding="utf-8",
        )

        config = load_config(tmp_path)

        assert isinstance(config.projects["chat_123"], ProjectConfig)

    def test_does_not_create_default_project_when_json_exists(self, tmp_path):
        (tmp_path / ".env").write_text("TELEGRAM_TOKEN=tok-abc\nTIMETTA_PROJECT_ID=p-env\n", encoding="utf-8")
        (tmp_path / "telegram_projects.json").write_text(
            json.dumps({"custom": {"project_id": "p-custom"}}),
            encoding="utf-8",
        )

        config = load_config(tmp_path)

        assert "default" not in config.projects
        assert "custom" in config.projects


class TestLoadConfigMissingToken:
    """No TELEGRAM_TOKEN → raises SystemExit."""

    def test_raises_system_exit_when_token_missing(self, tmp_path):
        (tmp_path / ".env").write_text("TIMETTA_PROJECT_ID=p-001\n", encoding="utf-8")

        with pytest.raises(SystemExit):
            load_config(tmp_path)

    def test_raises_system_exit_when_token_empty_in_env_file(self, tmp_path):
        (tmp_path / ".env").write_text("TELEGRAM_TOKEN=\n", encoding="utf-8")

        with pytest.raises(SystemExit):
            load_config(tmp_path)

    def test_raises_system_exit_when_no_env_file(self, tmp_path):
        # tmp_path has no .env and TELEGRAM_TOKEN not set in environment
        with patch.dict("os.environ", {}, clear=False):
            # Ensure TELEGRAM_TOKEN is absent from environment
            import os
            env_backup = os.environ.pop("TELEGRAM_TOKEN", None)
            try:
                with pytest.raises(SystemExit):
                    load_config(tmp_path)
            finally:
                if env_backup is not None:
                    os.environ["TELEGRAM_TOKEN"] = env_backup
