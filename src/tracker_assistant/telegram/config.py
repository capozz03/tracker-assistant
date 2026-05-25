from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..shared.io_utils import load_env

logger = logging.getLogger(__name__)


@dataclass
class ProjectConfig:
    project_id: str
    sprint_id: str = ""
    project_path: Path | None = None
    vps_remote: str | None = None


@dataclass
class BotConfig:
    token: str
    root: Path
    projects: dict[str, ProjectConfig]


def load_config(root: Path) -> BotConfig:
    """Load bot configuration from .env and optional telegram_projects.json.

    Reads TELEGRAM_TOKEN from .env (via load_env). If telegram_projects.json
    exists in root, loads project definitions from it. Otherwise creates a
    default project using TIMETTA_PROJECT_ID from env (empty string if absent).

    Raises:
        SystemExit: if TELEGRAM_TOKEN is not set.
    """
    logger.debug("load_config: reading env from root=%s", root)
    env = load_env(root)

    token = env.get("TELEGRAM_TOKEN", "")
    if not token:
        raise SystemExit("ERROR: TELEGRAM_TOKEN не задан")

    projects_file = root / "telegram_projects.json"

    if projects_file.exists():
        logger.debug("load_config: loading projects from %s", projects_file)
        raw = json.loads(projects_file.read_text(encoding="utf-8"))
        projects: dict[str, ProjectConfig] = {}
        for name, cfg in raw.items():
            projects[name] = ProjectConfig(
                project_id=cfg.get("project_id", ""),
                sprint_id=cfg.get("sprint_id", ""),
                project_path=Path(cfg["project_path"]) if cfg.get("project_path") else None,
                vps_remote=cfg.get("vps_remote"),
            )
    else:
        logger.debug("load_config: telegram_projects.json not found, creating default project")
        default_project_id = env.get("TIMETTA_PROJECT_ID", "")
        projects = {
            "default": ProjectConfig(project_id=default_project_id),
        }

    config = BotConfig(token=token, root=root, projects=projects)
    logger.debug("load_config: root=%s, projects=%d", root, len(config.projects))
    return config
