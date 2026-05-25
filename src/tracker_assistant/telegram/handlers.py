from __future__ import annotations

"""Telegram message handlers: text, photo, document, and slash commands."""

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.ext import (
    BaseHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ..submit import build_adapter, submit_requirements
from ..shared.io_utils import load_cached
from .config import BotConfig, ProjectConfig
from .projects import ProjectRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_forwarded_text(message: Any) -> str | None:
    """Return text from a forwarded message, or None if not forwarded."""
    if not message.forward_date:
        return None
    # Forwarded messages keep original text/caption in the same fields
    return message.text or message.caption or None


def _format_results(results: list[dict[str, Any]]) -> str:
    """Format submit_requirements results as a user-friendly reply."""
    n = len(results)
    if not results:
        return "⚠️ Задачи не созданы."
    lines = [f"✅ Создано {n} задач{'а' if n == 1 else 'и' if 2 <= n <= 4 else ''}:"]
    for r in results:
        summary = r.get("summary", "—")
        url = r.get("url", "")
        if url:
            lines.append(f"• {summary} — {url}")
        else:
            lines.append(f"• {summary}")
    return "\n".join(lines)


def _run_submit(
    text: str,
    project: ProjectConfig,
    root: Path,
) -> list[dict[str, Any]]:
    """Synchronous wrapper that builds adapter and calls submit_requirements."""
    adapter = build_adapter(root)
    users = load_cached(root, "users", adapter.get_users)
    tags = load_cached(root, "tags", adapter.get_tags)
    return submit_requirements(
        requirements=text,
        project_id=project.project_id,
        adapter=adapter,
        users=users,
        tags=tags,
        project_path=project.project_path,
        root=root,
        sprint_id=project.sprint_id,
    )


# ---------------------------------------------------------------------------
# Handler factories
# ---------------------------------------------------------------------------


def make_handlers(
    registry: ProjectRegistry,
    config: BotConfig,
) -> list[BaseHandler]:
    """Build and return all handlers for the Application.

    Args:
        registry: ProjectRegistry for chat → project mapping.
        config: BotConfig with root path and token.

    Returns:
        List of BaseHandler instances to register with Application.
    """

    async def handle_text(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle plain-text and forwarded text messages."""
        assert update.message is not None  # noqa: S101
        chat_id = update.effective_chat.id if update.effective_chat else 0
        logger.info("[tg] text: chat=%s", chat_id)

        # Prefer forwarded text, then regular text
        forwarded = _extract_forwarded_text(update.message)
        text = forwarded or update.message.text or ""
        if not text.strip():
            await update.message.reply_text("⚠️ Сообщение пустое — нечего обрабатывать.")
            return

        logger.info("[tg] text: chat=%s len=%d", chat_id, len(text))

        try:
            project = registry.get_project(chat_id)
        except KeyError:
            await update.message.reply_text(
                "❌ Проект не настроен. Добавьте запись в telegram_projects.json."
            )
            return

        if not project.project_id:
            await update.message.reply_text(
                "❌ project_id не задан. Проверьте telegram_projects.json или TIMETTA_PROJECT_ID в .env."
            )
            return

        await update.message.reply_text("⏳ Создаю задачи…")
        try:
            results = await asyncio.to_thread(
                _run_submit, text, project, config.root
            )
        except Exception as exc:
            logger.exception("[tg] submit failed: chat=%s", chat_id)
            await update.message.reply_text(f"❌ Ошибка создания задач: {exc}")
            return

        # Save last task ids for photo-without-caption flow
        context.user_data["last_task_ids"] = [r["id"] for r in results]
        await update.message.reply_text(_format_results(results))

    async def handle_photo(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle photo messages: submit caption (if any) then attach photo."""
        assert update.message is not None  # noqa: S101
        chat_id = update.effective_chat.id if update.effective_chat else 0

        # Largest available photo resolution
        photo = update.message.photo[-1]
        logger.info(
            "[tg] photo: chat=%s file_id=%s",
            chat_id,
            photo.file_id,
        )

        caption = update.message.caption or ""
        task_ids: list[str] = []

        if caption.strip():
            # Submit caption as requirements, then attach photo
            try:
                project = registry.get_project(chat_id)
            except KeyError:
                await update.message.reply_text(
                    "❌ Проект не настроен. Добавьте запись в telegram_projects.json."
                )
                return

            if not project.project_id:
                await update.message.reply_text(
                    "❌ project_id не задан. Проверьте конфигурацию."
                )
                return

            await update.message.reply_text("⏳ Создаю задачи…")
            try:
                results = await asyncio.to_thread(
                    _run_submit, caption, project, config.root
                )
            except Exception as exc:
                logger.exception("[tg] photo submit failed: chat=%s", chat_id)
                await update.message.reply_text(f"❌ Ошибка создания задач: {exc}")
                return

            task_ids = [r["id"] for r in results]
            context.user_data["last_task_ids"] = task_ids
            await update.message.reply_text(_format_results(results))
        else:
            # No caption — attach to last created tasks
            task_ids = context.user_data.get("last_task_ids", [])
            if not task_ids:
                await update.message.reply_text(
                    "⚠️ Нет задач для прикрепления. Сначала отправьте текст с требованиями."
                )
                return

        # Download and attach photo
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / f"{photo.file_id}.jpg"
            tg_file = await photo.get_file()
            await tg_file.download_to_drive(tmp_path)

            file_size = tmp_path.stat().st_size
            logger.info(
                "[tg] photo: chat=%s file_size=%d", chat_id, file_size
            )

            try:
                adapter = build_adapter(config.root)
            except SystemExit as exc:
                await update.message.reply_text(f"❌ Ошибка конфигурации: {exc}")
                return

            attached = 0
            for task_id in task_ids:
                if not task_id:
                    continue
                result = await asyncio.to_thread(
                    adapter.attach_file, task_id, str(tmp_path)
                )
                if result is not None:
                    attached += 1

        if attached:
            await update.message.reply_text(
                f"📎 Фото прикреплено к {attached} задач{'е' if attached == 1 else 'ам'}."
            )
        else:
            await update.message.reply_text(
                "⚠️ Не удалось прикрепить фото (Timetta может не поддерживать вложения)."
            )

    async def handle_document(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle document/file messages: attach to last tasks."""
        assert update.message is not None  # noqa: S101
        chat_id = update.effective_chat.id if update.effective_chat else 0
        doc = update.message.document
        if doc is None:
            return
        logger.info(
            "[tg] document: chat=%s file_name=%s", chat_id, doc.file_name
        )

        caption = update.message.caption or ""
        task_ids: list[str] = []

        if caption.strip():
            try:
                project = registry.get_project(chat_id)
            except KeyError:
                await update.message.reply_text(
                    "❌ Проект не настроен. Добавьте запись в telegram_projects.json."
                )
                return

            if not project.project_id:
                await update.message.reply_text(
                    "❌ project_id не задан. Проверьте конфигурацию."
                )
                return

            await update.message.reply_text("⏳ Создаю задачи…")
            try:
                results = await asyncio.to_thread(
                    _run_submit, caption, project, config.root
                )
            except Exception as exc:
                logger.exception("[tg] doc submit failed: chat=%s", chat_id)
                await update.message.reply_text(f"❌ Ошибка создания задач: {exc}")
                return

            task_ids = [r["id"] for r in results]
            context.user_data["last_task_ids"] = task_ids
            await update.message.reply_text(_format_results(results))
        else:
            task_ids = context.user_data.get("last_task_ids", [])
            if not task_ids:
                await update.message.reply_text(
                    "⚠️ Нет задач для прикрепления. Сначала отправьте текст с требованиями."
                )
                return

        # Download and attach
        suffix = Path(doc.file_name or "file").suffix or ".bin"
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / f"{doc.file_id}{suffix}"
            tg_file = await doc.get_file()
            await tg_file.download_to_drive(tmp_path)

            try:
                adapter = build_adapter(config.root)
            except SystemExit as exc:
                await update.message.reply_text(f"❌ Ошибка конфигурации: {exc}")
                return

            attached = 0
            for task_id in task_ids:
                if not task_id:
                    continue
                result = await asyncio.to_thread(
                    adapter.attach_file, task_id, str(tmp_path)
                )
                if result is not None:
                    attached += 1

        if attached:
            await update.message.reply_text(
                f"📎 Файл прикреплён к {attached} задач{'е' if attached == 1 else 'ам'}."
            )
        else:
            await update.message.reply_text(
                "⚠️ Не удалось прикрепить файл (Timetta может не поддерживать вложения)."
            )

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------

    async def cmd_start(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /start command."""
        chat_id = update.effective_chat.id if update.effective_chat else 0
        logger.debug("[tg] command: /start chat=%s", chat_id)
        await update.message.reply_text(
            "👋 Привет! Я помогу создавать задачи в Timetta.\n\n"
            "Просто напишите требования — я автоматически создам задачи.\n\n"
            "Команды:\n"
            "  /project — текущий проект чата\n"
            "  /tasks — последние созданные задачи\n\n"
            "Поддерживаю: текст, пересланные сообщения, фото и файлы."
        )

    async def cmd_project(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /project command — show current chat's project."""
        chat_id = update.effective_chat.id if update.effective_chat else 0
        logger.debug("[tg] command: /project chat=%s", chat_id)
        try:
            project = registry.get_project(chat_id)
        except KeyError:
            await update.message.reply_text("❌ Проект не настроен.")
            return
        sprint_info = f"\nСпринт: `{project.sprint_id}`" if project.sprint_id else ""
        await update.message.reply_text(
            f"📂 Текущий проект:\n"
            f"ID: `{project.project_id}`{sprint_info}",
            parse_mode="Markdown",
        )

    async def cmd_tasks(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /tasks command — show last created task IDs."""
        chat_id = update.effective_chat.id if update.effective_chat else 0
        logger.debug("[tg] command: /tasks chat=%s", chat_id)
        last_ids: list[str] = context.user_data.get("last_task_ids", [])
        if not last_ids:
            await update.message.reply_text("ℹ️ Последние задачи не найдены в этой сессии.")
            return
        lines = ["🗂 Последние задачи:"]
        for tid in last_ids:
            if tid:
                lines.append(f"• https://app.timetta.com/issues/{tid}")
        await update.message.reply_text("\n".join(lines))

    # ------------------------------------------------------------------
    # Assemble handler list
    # ------------------------------------------------------------------
    return [
        CommandHandler("start", cmd_start),
        CommandHandler("project", cmd_project),
        CommandHandler("tasks", cmd_tasks),
        MessageHandler(filters.PHOTO, handle_photo),
        MessageHandler(filters.Document.ALL, handle_document),
        # Text last: catches forwarded messages and plain text
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
    ]
