from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def configure_logging(cli_level: str | None = None) -> None:
    """Configure logging: CLI flag > LOG_LEVEL env > WARNING (prod default).

    Priority:
    1. cli_level argument (from --log-level CLI flag)
    2. LOG_LEVEL environment variable
    3. "WARNING" as default (safe for production)

    Args:
        cli_level: Level string passed from CLI (e.g. "DEBUG", "INFO", None if not provided).
    """
    if cli_level is not None:
        level = cli_level
        source = "cli"
    elif os.environ.get("LOG_LEVEL"):
        level = os.environ["LOG_LEVEL"]
        source = "env"
    else:
        level = "WARNING"
        source = "default"

    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        logger.warning("logging: invalid level %r, falling back to WARNING", level)
        numeric_level = logging.WARNING
        level = "WARNING"

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.debug("logging configured: level=%s (source=%s)", level, source)
