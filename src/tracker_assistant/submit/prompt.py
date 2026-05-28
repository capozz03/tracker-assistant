from __future__ import annotations

"""Промпт-шаблон и утилиты разрешения тегов для submit pipeline."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """\
Преобразуй требования ниже в JSON-массив задач Timetta. Верни только JSON, без пояснений.

## Стек проекта
{stack_context}

## Доступные теги (используй только эти UUID)
{tags}

## Доступные исполнители (используй только эти UUID)
{users}

## Требования
{requirements}

---

## Правила создания задач

**Разбивка по слоям:**
- Если задача затрагивает И фронтенд, И бэкенд — создай ДВЕ задачи:
  одну с тегом «Фронтенд» и одну с тегом «Бекенд».
- Если задача только одного слоя — одна задача.
- Если задача организационная (аналитика, документация) — одна задача.

**Каждая задача содержит:**
- `summary`: краткое название задачи. НЕ добавляй префикс «Frontend:», «Backend:», «Фронтенд:» и т.п. — слой уже указан в тегах.
- `description`: Markdown-описание. Заголовки разделов оформляй ТОЛЬКО так: `#### ***Название раздела***` (h4 + жирный курсив). Структура: контекст, что сделать, критерии приёмки.
- `tags`: массив из 1-2 UUID из списка выше (слой + тематический при наличии)
- `assignee`: UUID исполнителя если имя явно подходит, иначе ""
- `project_id`: "{project_id}" — не менять

**Не выдумывай UUID.** Используй только те, что в списках выше.

Верни ТОЛЬКО валидный JSON-массив без markdown-обёртки и пояснений:
[
  {{
    "project_id": "{project_id}",
    "summary": "...",
    "description": "...",
    "tags": ["uuid"],
    "assignee": "",
    "comments": [],
    "attachments": []
  }}
]
"""


def build_prompt(
    requirements: str,
    stack_context: str,
    tags: list[dict[str, Any]],
    users: list[dict[str, Any]],
    project_id: str,
) -> str:
    """Сформировать промпт для Claude из всех доступных данных."""
    tags_text = "\n".join(
        f"  - id={t.get('id', '')} name={t.get('name', '')}" for t in tags
    ) or "  (теги не найдены)"

    users_text = "\n".join(
        f"  - id={u.get('id', '')} name={u.get('displayName', '')}" for u in users
    ) or "  (исполнители не найдены)"

    return PROMPT_TEMPLATE.format(
        stack_context=stack_context,
        tags=tags_text,
        users=users_text,
        requirements=requirements,
        project_id=project_id,
    )


def resolve_tags(
    tag_values: list[str],
    known_tags: list[dict[str, Any]],
) -> list[str]:
    """Разрешает имена или UUID тегов в валидные UUID из known_tags.

    Claude иногда возвращает имена тегов ("Фронтенд", "backend") вместо UUID.
    Принимает любой формат, возвращает только корректные UUID.
    """
    id_set: set[str] = {t.get("id", "") for t in known_tags if t.get("id")}
    name_to_id: dict[str, str] = {
        t.get("name", "").lower(): t.get("id", "")
        for t in known_tags
        if t.get("name") and t.get("id")
    }
    code_to_id: dict[str, str] = {
        t.get("code", "").lower(): t.get("id", "")
        for t in known_tags
        if t.get("code") and t.get("id")
    }

    result: list[str] = []
    for val in tag_values:
        val_str = str(val).strip()
        if val_str in id_set:
            logger.debug("[TAG] ✓ UUID passthrough: %s", val_str)
            result.append(val_str)
        elif val_str.lower() in name_to_id:
            resolved = name_to_id[val_str.lower()]
            logger.info("[TAG] Имя → UUID: %r → %s", val_str, resolved)
            result.append(resolved)
        elif val_str.lower() in code_to_id:
            resolved = code_to_id[val_str.lower()]
            logger.info("[TAG] Код → UUID: %r → %s", val_str, resolved)
            result.append(resolved)
        else:
            logger.warning("[TAG] Тег не найден в справочнике, пропускается: %r", val_str)
    return result
