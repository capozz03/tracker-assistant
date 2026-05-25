from __future__ import annotations

"""Telegram bot factory and polling entry point."""

import logging

from telegram.ext import Application, ApplicationBuilder

from .config import BotConfig
from .projects import ProjectRegistry

logger = logging.getLogger(__name__)


def build_application(config: BotConfig) -> Application:
    """Create and configure the Telegram Application with all handlers registered.

    Args:
        config: Loaded BotConfig containing token and project definitions.

    Returns:
        Configured Application ready to run.
    """
    logger.debug("build_application: building with token=***")
    registry = ProjectRegistry(config.projects)

    app: Application = (
        ApplicationBuilder()
        .token(config.token)
        .build()
    )

    # Import here to avoid circular deps at module load time
    from .handlers import make_handlers  # noqa: PLC0415

    for handler in make_handlers(registry, config):
        app.add_handler(handler)

    logger.info(
        "bot: application built, проектов=%d",
        len(config.projects),
    )
    return app


def run_bot(config: BotConfig) -> None:
    """Build the Application and start polling for updates.

    Blocks until the bot is stopped (e.g. via Ctrl-C or OS signal).

    Args:
        config: Loaded BotConfig.
    """
    logger.info("bot: запускаем polling, проектов=%d", len(config.projects))
    app = build_application(config)
    app.run_polling()
