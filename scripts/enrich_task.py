from __future__ import annotations

"""enrich_task.py — тонкая CLI-обёртка над tracker_assistant.enrich."""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tracker_assistant.enrich import enrich_task, build_adapter
from tracker_assistant.shared.io_utils import load_cached


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

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )

    root = Path(args.root).resolve()

    # --- Входные данные ---
    if args.input:
        input_path = Path(args.input)
        if not input_path.is_absolute():
            input_path = root / input_path
        if not input_path.exists():
            raise SystemExit(f"ERROR: файл не найден: {input_path}")
        raw_task: dict[str, Any] = json.loads(input_path.read_text(encoding="utf-8"))
    else:
        raw_text = sys.stdin.read()
        if not raw_text.strip():
            raise SystemExit("ERROR: нет входных данных (используй --input или stdin)")
        raw_task = json.loads(raw_text)

    # --- Адаптер + кеши ---
    adapter = build_adapter(root)
    users = load_cached(root, "users", adapter.get_users, no_cache=args.no_cache)
    tags  = load_cached(root, "tags",  adapter.get_tags,  no_cache=args.no_cache)

    # --- Обогащение ---
    enriched = enrich_task(raw_task, users, tags, root)
    output_json = json.dumps(enriched, ensure_ascii=False, indent=2)

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = root / output_path
        output_path.write_text(output_json, encoding="utf-8")
    else:
        print(output_json)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
