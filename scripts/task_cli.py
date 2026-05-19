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

from tracker_assistant.adapters.timetta_adapter import TimettaAdapter
from tracker_assistant.io_utils import load_env
from tracker_assistant.models import Task
from tracker_assistant.pipeline import create_task, list_projects


def _build_adapter(root: Path) -> TimettaAdapter:
    env = load_env(root)
    token = env.get("TIMETTA_TOKEN") or os.environ.get("TIMETTA_TOKEN", "")
    if not token:
        raise SystemExit(
            "ERROR: TIMETTA_TOKEN must be set in .env or environment variables"
        )
    logging.debug("Adapter: Timetta token loaded")
    return TimettaAdapter(token=token)


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
    logging.debug("Loaded task from %s: project=%s summary=%r", input_path, task.project_id, task.summary)
    adapter = _build_adapter(root)
    result = create_task(adapter, task, root=root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_add_comment(args: argparse.Namespace) -> int:
    adapter = _build_adapter(Path(args.root).resolve())
    logging.debug("Adding comment to task %s", args.issue)
    result = adapter.add_comment(args.issue, args.text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_attach_file(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    filepath = Path(args.file)
    if not filepath.is_absolute():
        filepath = root / filepath
    adapter = _build_adapter(root)
    logging.debug("Attaching %s to task %s", filepath.name, args.issue)
    result = adapter.attach_file(args.issue, str(filepath))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Timetta CLI")
    parser.add_argument("--root", default=".", help="Path to tracker-assistant root (contains .env)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-projects", help="List all Timetta projects")

    create_p = sub.add_parser("create", help="Create task from JSON file")
    create_p.add_argument("--input", required=True, help="Path to task JSON file")

    comment_p = sub.add_parser("add-comment", help="Add comment to task")
    comment_p.add_argument("--issue", required=True, help="Task ID")
    comment_p.add_argument("--text", required=True, help="Comment text")

    attach_p = sub.add_parser("attach-file", help="Attach file to task")
    attach_p.add_argument("--issue", required=True, help="Task ID")
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
