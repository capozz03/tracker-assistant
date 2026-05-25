from __future__ import annotations

import logging

from .config import ProjectConfig

logger = logging.getLogger(__name__)


class ProjectRegistry:
    """Maps chat identifiers to ProjectConfig instances.

    Keys in the projects dict follow two conventions:
    - ``"chat_<chat_id>"`` — per-chat override (e.g. ``"chat_123456789"``)
    - ``"default"`` — fallback for chats without a dedicated entry

    Args:
        projects: Mapping of key → ProjectConfig, typically loaded from
            BotConfig.projects via load_config().
    """

    def __init__(self, projects: dict[str, ProjectConfig]) -> None:
        logger.debug("ProjectRegistry.__init__: loaded %d project(s)", len(projects))
        self._projects = projects

    def get_project(self, chat_id: str | int) -> ProjectConfig:
        """Return the ProjectConfig for the given chat_id.

        Looks up ``f"chat_{chat_id}"`` first. Falls back to ``"default"``
        when no per-chat entry exists.

        Args:
            chat_id: Telegram chat identifier (int or string).

        Returns:
            Matching ProjectConfig.

        Raises:
            KeyError: if neither ``f"chat_{chat_id}"`` nor ``"default"``
                exists in the registry.
        """
        key = f"chat_{chat_id}"
        if key in self._projects:
            project = self._projects[key]
            logger.debug(
                "ProjectRegistry.get_project: chat_id=%s → project_id=%s (per-chat)",
                chat_id,
                project.project_id,
            )
            return project

        if "default" in self._projects:
            project = self._projects["default"]
            logger.debug(
                "ProjectRegistry.get_project: chat_id=%s → project_id=%s (default)",
                chat_id,
                project.project_id,
            )
            return project

        raise KeyError("No default project configured")

    def list_projects(self) -> list[tuple[str, ProjectConfig]]:
        """Return all registered projects as (key, ProjectConfig) tuples.

        Returns:
            List of (key, ProjectConfig) pairs in insertion order.
        """
        result = list(self._projects.items())
        logger.debug("ProjectRegistry.list_projects: returning %d project(s)", len(result))
        return result
