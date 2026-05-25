from __future__ import annotations

"""CLI entry point for the Telegram bot interface.

Usage:
    uv run task-telegram
    uv run task-telegram --root /path/to/project
    uv run task-telegram --log-level DEBUG
    uv run task-telegram --dry-run
"""

import argparse
import logging
import sys
from pathlib import Path

from .config import load_config
from .bot import run_bot

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="task-telegram",
        description="Telegram bot interface for Timetta task management.",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Project root directory containing .env and telegram_projects.json (default: current dir).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and exit without starting the bot.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: parse args, load config, optionally run bot.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 = success, non-zero = error).
    """
    args = _parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    root = Path(args.root).resolve()
    logger.info("cli: root=%s dry_run=%s", root, args.dry_run)

    try:
        config = load_config(root)
    except SystemExit as exc:
        # load_config raises SystemExit for missing token — surface the message
        print(str(exc), file=sys.stderr)
        return 1

    logger.debug(
        "cli: config loaded — token=***, projects=%d",
        len(config.projects),
    )

    if args.dry_run:
        print(f"✅ Конфиг валиден: {len(config.projects)} проект(ов) загружено.")
        for key, project in config.projects.items():
            print(f"  {key}: project_id={project.project_id!r}")
        return 0

    run_bot(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
