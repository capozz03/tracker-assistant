from __future__ import annotations

"""submit cli — тонкая CLI-обёртка над tracker_assistant.submit.

Использование:
    uv run task-submit \\
        --requirements-file tasks.md \\
        --project-id <uuid> \\
        --sprint-id <uuid>

    # TIMETTA_PROJECT_ID можно прописать в .env вместо --project-id
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from tracker_assistant.submit import submit_requirements, build_adapter
from tracker_assistant.shared.io_utils import load_cached, load_env

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Создать задачи в Timetta из текстовых требований",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--root", default=".",
                        help="Путь к корню tracker-assistant (содержит .env)")
    parser.add_argument("--requirements",
                        help="Текст требований напрямую")
    parser.add_argument("--requirements-file",
                        help="Путь к файлу с требованиями (.md/.txt)")
    parser.add_argument("--project-id",
                        help="UUID проекта в Timetta (или TIMETTA_PROJECT_ID в .env)")
    parser.add_argument("--project-path",
                        help="Путь к анализируемой кодовой базе (необязательно)")
    parser.add_argument("--sprint-id",
                        help="UUID спринта в Timetta (необязательно)")
    parser.add_argument("--no-cache", action="store_true",
                        help="Игнорировать кеш пользователей/тегов")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )

    root = Path(args.root).resolve()

    # --- Требования ---
    if args.requirements:
        requirements = args.requirements
    elif args.requirements_file:
        req_path = Path(args.requirements_file)
        if not req_path.is_absolute():
            req_path = root / req_path
        if not req_path.exists():
            raise SystemExit(f"ERROR: файл не найден: {req_path}")
        requirements = req_path.read_text(encoding="utf-8")
        logger.info("Требования загружены из %s (%d символов)", req_path, len(requirements))
    elif not sys.stdin.isatty():
        requirements = sys.stdin.read().strip()
        if not requirements:
            raise SystemExit("ERROR: пустой stdin")
    else:
        raise SystemExit(
            "ERROR: укажи --requirements \"текст\" или --requirements-file path.md"
        )

    # --- Project ID ---
    env = load_env(root)
    project_id = (
        args.project_id
        or env.get("TIMETTA_PROJECT_ID")
        or os.environ.get("TIMETTA_PROJECT_ID", "")
    )
    if not project_id:
        raise SystemExit(
            "ERROR: укажи --project-id <uuid> или добавь TIMETTA_PROJECT_ID в .env"
        )

    # --- Адаптер + кеши ---
    adapter = build_adapter(root)
    users = load_cached(root, "users", adapter.get_users, no_cache=args.no_cache)
    tags  = load_cached(root, "tags",  adapter.get_tags,  no_cache=args.no_cache)
    logger.debug("Загружено: %d тегов, %d исполнителей", len(tags), len(users))

    # --- Пайплайн ---
    results = submit_requirements(
        requirements=requirements,
        project_id=project_id,
        adapter=adapter,
        users=users,
        tags=tags,
        project_path=Path(args.project_path).resolve() if args.project_path else None,
        root=root,
        sprint_id=args.sprint_id or "",
    )

    # --- Вывод ---
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\n✅ Создано задач: {len(results)}", file=sys.stderr)
    for r in results:
        print(f"  • {r['summary']}", file=sys.stderr)
        if r.get("url"):
            print(f"    {r['url']}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
