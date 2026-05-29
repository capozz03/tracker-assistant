from __future__ import annotations

"""Обогащение задачи через claude -p."""

import json
import logging
import os
from pathlib import Path
from typing import Any

from ..timetta.adapter import TimettaAdapter
from ..shared.claude_client import call_claude_dict
from ..shared.io_utils import load_env

logger = logging.getLogger(__name__)

ENRICHMENT_PROMPT_TEMPLATE = """\
Ты — ассистент по созданию задач для команды разработчиков.

## Контекст проекта
{codebase_hint}

## Доступные теги
{tags}

## Доступные исполнители
{users}

## Сырое описание задачи
{raw_task}

## Инструкции

Проанализируй сырое описание задачи и верни обогащённый JSON со следующими полями:
1. `summary` — чёткое, профессиональное название задачи (краткое)
2. `description` — подробное описание в Markdown (контекст, что нужно сделать, критерии приёмки)
3. `tags` — выбери 1-3 ID тегов из доступных, которые лучше всего подходят (бэкенд/фронтенд/и т.д.). \
Копируй UUID тега дословно из списка выше; не переводи имена на английский и не выдумывай ID. \
Если подходящего тега нет — пустой массив
4. `assignee` — выбери ID пользователя, который лучше всего подходит по имени/логину; \
оставь пустую строку "", если не ясно
5. Сохрани все существующие поля из сырой задачи (project_id, task_type и др.)

Верни ТОЛЬКО валидный JSON без пояснений, строго в формате:
{{
  "project_id": "...",
  "summary": "...",
  "description": "...",
  "tags": ["tag-uuid"],
  "assignee": "user-uuid-or-empty",
  "comments": [],
  "attachments": []
}}
"""


def get_codebase_context(root: Path) -> str:
    """Прочитать краткий контекст проекта из DESCRIPTION.md или README.md."""
    desc_path = root / ".ai-factory" / "DESCRIPTION.md"
    if desc_path.exists():
        return desc_path.read_text(encoding="utf-8")[:1000]
    readme = root / "README.md"
    if readme.exists():
        return readme.read_text(encoding="utf-8")[:1000]
    return "Python-клиент для Timetta API управления задачами."


def build_adapter(root: Path) -> TimettaAdapter:
    """Создать TimettaAdapter из .env в root."""
    env = load_env(root)
    token = env.get("TIMETTA_TOKEN") or os.environ.get("TIMETTA_TOKEN", "")
    if not token:
        raise SystemExit("ERROR: set TIMETTA_TOKEN in .env")
    tags_dir_id = (
        env.get("TIMETTA_TAGS_DIR_ID")
        or os.environ.get("TIMETTA_TAGS_DIR_ID", "")
        or TimettaAdapter.DEFAULT_TAGS_DIR_ID
    )
    logger.debug("build_adapter: tags_dir_id=%s", tags_dir_id)
    return TimettaAdapter(token=token, tags_dir_id=tags_dir_id)


def enrich_task(
    raw_task: dict[str, Any],
    users: list[dict[str, Any]],
    tags: list[dict[str, Any]],
    root: Path,
) -> dict[str, Any]:
    """Обогатить сырую задачу через claude -p."""
    tags_summary = "\n".join(
        f"  - id={t.get('id', '')} name={t.get('name', '')}" for t in tags
    )
    users_summary = "\n".join(
        f"  - id={u.get('id', '')} name={u.get('displayName', '')} login={u.get('login', '')}"
        for u in users
    )
    codebase_hint = get_codebase_context(root)

    prompt = ENRICHMENT_PROMPT_TEMPLATE.format(
        raw_task=json.dumps(raw_task, ensure_ascii=False, indent=2),
        tags=tags_summary or "  (нет доступных тегов)",
        users=users_summary or "  (нет доступных исполнителей)",
        codebase_hint=codebase_hint,
    )

    enriched = call_claude_dict(prompt)
    logger.debug("enrich_task: enriched summary=%r", enriched.get("summary", ""))
    return enriched
