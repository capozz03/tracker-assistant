from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tracker_assistant.adapters.yandex_tracker_adapter import YandexTrackerAdapter
from tracker_assistant.io_utils import load_env
from tracker_assistant.models import Task
from tracker_assistant.pipeline import create_task, list_projects


def _build_adapter(root: Path) -> YandexTrackerAdapter:
    env = load_env(root)
    token = env.get("YANDEX_TRACKER_TOKEN") or os.environ.get("YANDEX_TRACKER_TOKEN", "")
    org_id = env.get("YANDEX_TRACKER_ORG_ID") or os.environ.get("YANDEX_TRACKER_ORG_ID", "")
    org_type = env.get("YANDEX_TRACKER_ORG_TYPE") or os.environ.get("YANDEX_TRACKER_ORG_TYPE", "cloud")
    if not token or not org_id:
        raise SystemExit(
            "ERROR: YANDEX_TRACKER_TOKEN and YANDEX_TRACKER_ORG_ID must be set "
            "in .env or environment variables"
        )
    logging.debug("Adapter: org_id=%s org_type=%s", org_id, org_type)
    return YandexTrackerAdapter(token=token, org_id=org_id, org_type=org_type)


def _setup_logging(level: str) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_list_projects(args: argparse.Namespace) -> int:
    adapter = _build_adapter(Path(args.root).resolve())
    projects = list_projects(adapter)
    print(json.dumps(projects, ensure_ascii=False, indent=2))
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = root / input_path
    data = json.loads(input_path.read_text(encoding="utf-8"))
    task = Task.from_dict(data)
    logging.debug("Loaded task from %s: queue=%s summary=%r", input_path, task.queue, task.summary)
    adapter = _build_adapter(root)
    result = create_task(adapter, task, root=root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_add_comment(args: argparse.Namespace) -> int:
    adapter = _build_adapter(Path(args.root).resolve())
    logging.debug("Adding comment to %s", args.issue)
    result = adapter.add_comment(args.issue, args.text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_attach_file(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    filepath = Path(args.file)
    if not filepath.is_absolute():
        filepath = root / filepath
    adapter = _build_adapter(root)
    logging.debug("Attaching %s to %s", filepath.name, args.issue)
    result = adapter.attach_file(args.issue, str(filepath))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Yandex Tracker CLI")
    parser.add_argument("--root", default=".", help="Path to tracker-assistant root (contains .env)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-projects", help="List all projects")

    create_p = sub.add_parser("create", help="Create issue from JSON file")
    create_p.add_argument("--input", required=True, help="Path to task JSON file")

    comment_p = sub.add_parser("add-comment", help="Add comment to issue")
    comment_p.add_argument("--issue", required=True, help="Issue key, e.g. PROJ-123")
    comment_p.add_argument("--text", required=True, help="Comment text")

    attach_p = sub.add_parser("attach-file", help="Attach file to issue")
    attach_p.add_argument("--issue", required=True, help="Issue key, e.g. PROJ-123")
    attach_p.add_argument("--file", required=True, help="Path to file")

    args = parser.parse_args()
    _setup_logging(args.log_level)

    commands = {
        "list-projects": cmd_list_projects,
        "create": cmd_create,
        "add-comment": cmd_add_comment,
        "attach-file": cmd_attach_file,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
