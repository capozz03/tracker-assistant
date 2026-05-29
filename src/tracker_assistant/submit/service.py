from __future__ import annotations

"""Submit pipeline: требования → анализ стека → задачи в Timetta."""

import logging
import os
from pathlib import Path
from typing import Any

from ..timetta.adapter import TimettaAdapter
from ..timetta.models import Task
from ..timetta.service import create_task
from ..shared.claude_client import call_claude_list
from ..shared.io_utils import load_env
from .stack_detector import scan_project_stack, build_stack_context, empty_stack
from .prompt import build_prompt, resolve_tags

logger = logging.getLogger(__name__)

DEFAULT_TASK_TYPE = "968f71c6-6b38-4845-963a-b2d07ec95185"


def build_adapter(root: Path) -> TimettaAdapter:
    """Создать TimettaAdapter из .env в root."""
    env = load_env(root)
    token = env.get("TIMETTA_TOKEN") or os.environ.get("TIMETTA_TOKEN", "")
    if not token:
        raise RuntimeError("TIMETTA_TOKEN не задан (добавь в .env)")
    tags_dir_id = (
        env.get("TIMETTA_TAGS_DIR_ID")
        or os.environ.get("TIMETTA_TAGS_DIR_ID", "")
        or TimettaAdapter.DEFAULT_TAGS_DIR_ID
    )
    return TimettaAdapter(token=token, tags_dir_id=tags_dir_id)


def generate_tasks(
    requirements: str,
    project_id: str,
    project_path: Path | None,
    root: Path,
    *,
    tags: list[dict[str, Any]],
    users: list[dict[str, Any]],
    sprint_id: str = "",
    default_task_type: str = DEFAULT_TASK_TYPE,
) -> list[dict[str, Any]]:
    """Только генерация: requirements → stack → claude → нормализованные task_dict'ы.

    НИКАКИХ вызовов Timetta. Сырые `tags`/`assignee` остаются внутри dict'ов —
    для превью и последующего создания через `create_tasks`.
    """
    logger.debug("generate_tasks: project=%s sprint=%s", project_id, sprint_id)

    # 1. Анализ стека
    if project_path:
        stack = scan_project_stack(project_path)
    else:
        logger.info("--project-path не указан, стек не определяется")
        stack = empty_stack()

    stack_ctx = build_stack_context(stack)

    # 2. Формируем промпт и вызываем Claude
    prompt = build_prompt(requirements, stack_ctx, tags, users, project_id)
    task_dicts = call_claude_list(prompt)

    # 3. Нормализуем каждый dict (project_id / task_type / sprintId)
    for task_dict in task_dicts:
        task_dict.setdefault("project_id", project_id)
        if not task_dict.get("task_type"):
            task_dict["task_type"] = default_task_type
        if sprint_id:
            task_dict.setdefault("extra", {})["sprintId"] = sprint_id

    logger.info("generate_tasks: %d задач(и) сгенерировано", len(task_dicts))
    return task_dicts


def create_tasks(
    task_dicts: list[dict[str, Any]],
    *,
    adapter: TimettaAdapter,
    tags: list[dict[str, Any]],
    root: Path,
) -> list[dict[str, Any]]:
    """Создание подготовленных задач в Timetta: resolve_tags → create_task → update_task."""
    results: list[dict[str, Any]] = []
    total = len(task_dicts)
    for idx, task_dict in enumerate(task_dicts, 1):
        # Tags идут отдельным PATCH — POST /Issues не принимает теги
        raw_tags = task_dict.pop("tags", [])
        pending_tags = resolve_tags(raw_tags, tags)
        if raw_tags and not pending_tags:
            logger.warning("[TAG] Ни один тег не разрешён из %r", raw_tags)

        pending_assignee = task_dict.get("assignee", "")

        task = Task.from_dict(task_dict)
        logger.info("[%d/%d] Создаю: %r", idx, total, task.summary)

        created = create_task(adapter, task, root=root)
        task_id = created.get("id", "")

        if task_id and (pending_tags or pending_assignee):
            update_fields: dict[str, Any] = {}
            if pending_tags:
                update_fields["tags"] = pending_tags
            if pending_assignee:
                update_fields["assigneeId"] = pending_assignee
            logger.debug("[%d/%d] update tags=%s assignee=%s", idx, total, pending_tags, pending_assignee)
            adapter.update_task(task_id, **update_fields)

        results.append({
            "id":       task_id,
            "summary":  task.summary,
            "tags":     pending_tags,
            "assignee": pending_assignee,
            "url":      f"https://app.timetta.com/issues/{task_id}" if task_id else "",
        })
        logger.info("[%d/%d] Создана id=%s", idx, total, task_id)

    logger.info("create_tasks: %d создано", len(results))
    return results


def submit_requirements(
    requirements: str,
    project_id: str,
    adapter: TimettaAdapter,
    users: list[dict[str, Any]],
    tags: list[dict[str, Any]],
    project_path: Path | None,
    root: Path,
    sprint_id: str = "",
    default_task_type: str = DEFAULT_TASK_TYPE,
) -> list[dict[str, Any]]:
    """Полный пайплайн: requirements → stack → claude → create задачи в Timetta.

    Тонкая обёртка над `generate_tasks` + `create_tasks`; сохраняет прежнюю
    сигнатуру и результат для CLI (`task-submit`) и существующих тестов.
    """
    task_dicts = generate_tasks(
        requirements,
        project_id,
        project_path,
        root,
        tags=tags,
        users=users,
        sprint_id=sprint_id,
        default_task_type=default_task_type,
    )
    return create_tasks(task_dicts, adapter=adapter, tags=tags, root=root)
