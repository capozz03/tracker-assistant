from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .adapter import TimettaAdapter
from .models import Task

logger = logging.getLogger(__name__)


def list_projects(adapter: TimettaAdapter) -> list[dict[str, Any]]:
    logger.debug("list_projects: fetching from API")
    projects = adapter.get_projects()
    logger.debug("list_projects: returned %d projects", len(projects))
    return projects


def create_task(
    adapter: TimettaAdapter,
    task: Task,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    logger.debug(
        "create_task: project=%s summary=%r comments=%d attachments=%d",
        task.project_id, task.summary, len(task.comments), len(task.attachments),
    )
    result = adapter.create_task(task)
    task_id = result.get("id", "")
    logger.debug("create_task: task created id=%s", task_id)

    for i, text in enumerate(task.comments, 1):
        logger.debug("create_task: adding comment %d/%d to %s", i, len(task.comments), task_id)
        adapter.add_comment(task_id, text)

    for i, filepath in enumerate(task.attachments, 1):
        resolved = (root / filepath if root else Path(filepath)).resolve()
        logger.debug("create_task: attaching file %d/%d %s to %s", i, len(task.attachments), resolved.name, task_id)
        adapter.attach_file(task_id, str(resolved))

    logger.debug("create_task: done id=%s", task_id)
    return result
