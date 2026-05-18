from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .adapters.yandex_tracker_adapter import YandexTrackerAdapter
from .models import Task

logger = logging.getLogger(__name__)


def list_projects(adapter: YandexTrackerAdapter) -> list[dict[str, Any]]:
    logger.debug("list_projects: fetching from API")
    projects = adapter.get_projects()
    logger.debug("list_projects: returned %d projects", len(projects))
    return projects


def create_task(
    adapter: YandexTrackerAdapter,
    task: Task,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    logger.debug(
        "create_task: queue=%s summary=%r comments=%d attachments=%d",
        task.queue, task.summary, len(task.comments), len(task.attachments),
    )
    result = adapter.create_issue(task)
    issue_key = result.get("key", "")
    logger.debug("create_task: issue created key=%s", issue_key)

    for i, text in enumerate(task.comments, 1):
        logger.debug("create_task: adding comment %d/%d to %s", i, len(task.comments), issue_key)
        adapter.add_comment(issue_key, text)

    for i, filepath in enumerate(task.attachments, 1):
        resolved = (root / filepath if root else Path(filepath)).resolve()
        logger.debug("create_task: attaching file %d/%d %s to %s", i, len(task.attachments), resolved.name, issue_key)
        adapter.attach_file(issue_key, str(resolved))

    logger.debug("create_task: done key=%s", issue_key)
    return result
