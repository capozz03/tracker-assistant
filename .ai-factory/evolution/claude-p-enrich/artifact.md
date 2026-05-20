```python
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tracker_assistant.adapters.timetta_adapter import TimettaAdapter
from tracker_assistant.io_utils import load_cached, load_env

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
3. `tags` — выбери 1-3 ID тегов из доступных, которые лучше всего подходят (бэкенд/фронтенд/и т.д.)
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


def _build_adapter(root: Path) -> TimettaAdapter:
    env = load_env(root)
    token = env.get("TIMETTA_TOKEN") or os.environ.get("TIMETTA_TOKEN", "")
    if not token:
        raise SystemExit("ERROR: set TIMETTA_TOKEN in .env")
    logger.debug("_build_adapter: using TIMETTA_TOKEN")
    return TimettaAdapter(token=token)


def _get_codebase_context(root: Path) -> str:
    desc_path = root / ".ai-factory" / "DESCRIPTION.md"
    if desc_path.exists():
        return desc_path.read_text(encoding="utf-8")[:1000]
    readme = root / "README.md"
    if readme.exists():
        return readme.read_text(encoding="utf-8")[:1000]
    return "Python-клиент для Timetta API управления задачами."


def _call_claude(prompt: str) -> dict[str, Any]:
    logger.debug("_call_claude: prompt length=%d chars", len(prompt))
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"ERROR: claude -p завершился с ошибкой (код {result.returncode}):\n"
            f"{result.stderr.strip()}"
        )
    output = result.stdout.strip()
    logger.debug("_call_claude: received %d chars", len(output))
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"ERROR: claude -p вернул невалидный JSON: {exc}\n"
            f"Начало вывода: {output[:300]}"
        )


def enrich_task(
    raw_task: dict[str, Any],
    users: list[dict[str, Any]],
    tags: list[dict[str, Any]],
    root: Path,
) -> dict[str, Any]:
    tags_summary = "\n".join(
        f"  - id={t.get('id', '')} name={t.get('name', '')}" for t in tags
    )
    users_summary = "\n".join(
        f"  - id={u.get('id', '')} name={u.get('displayName', '')} login={u.get('login', '')}"
        for u in users
    )
    codebase_hint = _get_codebase_context(root)

    prompt = ENRICHMENT_PROMPT_TEMPLATE.format(
        raw_task=json.dumps(raw_task, ensure_ascii=False, indent=2),
        tags=tags_summary or "  (нет доступных тегов)",
        users=users_summary or "  (нет доступных исполнителей)",
        codebase_hint=codebase_hint,
    )

    enriched = _call_claude(prompt)
    logger.debug("enrich_task: enriched summary=%r", enriched.get("summary", ""))
    return enriched


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Обогатить задачу через claude -p перед созданием в Timetta"
    )
    parser.add_argument("--root", default=".", help="Путь к корню tracker-assistant (содержит .env)")
    parser.add_argument("--input", help="Путь к JSON-файлу с сырой задачей (по умолчанию: stdin)")
    parser.add_argument("--output", help="Путь для записи обогащённого task.json (по умолчанию: stdout)")
    parser.add_argument("--no-cache", action="store_true", help="Игнорировать кеш, загрузить свежие данные")
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    numeric = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )

    root = Path(args.root).resolve()

    if args.input:
        input_path = Path(args.input)
        if not input_path.is_absolute():
            input_path = root / input_path
        if not input_path.exists():
            raise SystemExit(f"ERROR: файл не найден: {input_path}")
        try:
            raw_task: dict[str, Any] = json.loads(input_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"ERROR: невалидный JSON в {input_path}: {exc}")
    else:
        raw_text = sys.stdin.read()
        if not raw_text.strip():
            raise SystemExit("ERROR: нет входных данных (используй --input или stdin)")
        try:
            raw_task = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"ERROR: невалидный JSON из stdin: {exc}")

    adapter = _build_adapter(root)

    users = load_cached(root, "users", adapter.get_users, no_cache=args.no_cache)
    tags = load_cached(root, "tags", adapter.get_tags, no_cache=args.no_cache)
    logger.debug("main: loaded %d tags, %d users", len(tags), len(users))

    enriched = enrich_task(raw_task, users, tags, root)

    output_json = json.dumps(enriched, ensure_ascii=False, indent=2)

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = root / output_path
        output_path.write_text(output_json, encoding="utf-8")
        logger.debug("main: результат записан в %s", output_path)
    else:
        print(output_json)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
