from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from tracker_assistant.timetta.adapter import TimettaAdapter
from tracker_assistant.timetta.models import Task
from tracker_assistant.timetta.service import create_task, list_projects
from tracker_assistant.shared.io_utils import load_cached, load_env


def _build_adapter(root: Path) -> TimettaAdapter:
    env = load_env(root)
    token = env.get("TIMETTA_TOKEN") or os.environ.get("TIMETTA_TOKEN", "")
    if not token:
        raise SystemExit("ERROR: set TIMETTA_TOKEN in .env")
    tags_dir_id = (
        env.get("TIMETTA_TAGS_DIR_ID")
        or os.environ.get("TIMETTA_TAGS_DIR_ID", "")
        or TimettaAdapter.DEFAULT_TAGS_DIR_ID
    )
    logging.debug("Adapter: using TIMETTA_TOKEN, tags_dir_id=%s", tags_dir_id)
    return TimettaAdapter(token=token, tags_dir_id=tags_dir_id)


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


def cmd_list_users(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    adapter = _build_adapter(root)
    users = load_cached(root, "users", adapter.get_users, no_cache=args.no_cache)
    logging.debug("list-users: returning %d users", len(users))
    print(json.dumps(users, ensure_ascii=False, indent=2))
    return 0


def cmd_list_tags(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    adapter = _build_adapter(root)
    tags = load_cached(root, "tags", adapter.get_tags, no_cache=args.no_cache)
    logging.debug("list-tags: returning %d tags", len(tags))
    print(json.dumps(tags, ensure_ascii=False, indent=2))
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


def cmd_update(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    adapter = _build_adapter(root)
    fields: dict = {}

    if args.assignee:
        fields["assigneeId"] = args.assignee
        logging.debug("update task %s: set assigneeId=%s", args.issue, args.assignee)

    if args.set_tags is not None:
        tag_ids = [t.strip() for t in args.set_tags.split(",") if t.strip()]
        fields["tags"] = tag_ids
        logging.debug("update task %s: set tags=%s", args.issue, tag_ids)

    if args.add_tag:
        existing = adapter.get_task(args.issue)
        current_tags: list = existing.get("tags", [])
        current_ids = [t["id"] if isinstance(t, dict) else t for t in current_tags]
        if args.add_tag not in current_ids:
            current_ids.append(args.add_tag)
        fields["tags"] = current_ids
        logging.debug("update task %s: add-tag=%s result=%s", args.issue, args.add_tag, current_ids)

    if not fields:
        logging.warning("update: no fields specified for task %s", args.issue)
        print(json.dumps({"warning": "no fields to update"}, ensure_ascii=False))
        return 0

    result = adapter.update_task(args.issue, **fields)
    logging.debug("update task %s: done", args.issue)
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

    users_p = sub.add_parser("list-users", help="List all Timetta users")
    users_p.add_argument("--no-cache", action="store_true", help="Bypass local cache and fetch fresh data")

    tags_p = sub.add_parser("list-tags", help="List all Timetta tags")
    tags_p.add_argument("--no-cache", action="store_true", help="Bypass local cache and fetch fresh data")

    create_p = sub.add_parser("create", help="Create task from JSON file")
    create_p.add_argument("--input", required=True, help="Path to task JSON file")

    update_p = sub.add_parser("update", help="Update task metadata (assignee, tags)")
    update_p.add_argument("--issue", required=True, help="Task ID")
    update_p.add_argument("--assignee", default="", help="Assignee user UUID")
    update_p.add_argument("--set-tags", default=None, help="Comma-separated tag UUIDs (replaces all tags)")
    update_p.add_argument("--add-tag", default="", help="Single tag UUID to add (keeps existing tags)")

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
        "list-users": cmd_list_users,
        "list-tags": cmd_list_tags,
        "create": cmd_create,
        "update": cmd_update,
        "add-comment": cmd_add_comment,
        "attach-file": cmd_attach_file,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
