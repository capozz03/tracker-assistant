from __future__ import annotations

"""Telegram message handlers: text, photo, document, and slash commands."""

import asyncio
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    BaseHandler,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ..submit import submit_requirements
from ..shared.io_utils import load_cached, load_env
from ..timetta import TimettaAdapter
from .config import BotConfig, ProjectConfig
from .pagination import make_select_keyboard, paginate
from .projects import ProjectRegistry
from .vps_sync import sync_codebase

logger = logging.getLogger(__name__)

# Page size for the live Timetta-API project list shown by /project.
_API_PROJECTS_PAGE_SIZE = 8


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_forwarded_text(message: Any) -> str | None:
    """Return text from a forwarded message, or None if not forwarded."""
    if not message.forward_origin:
        return None
    # Forwarded messages keep original text/caption in the same fields
    return message.text or message.caption or None


def _is_valid_project_id(project_id: str) -> bool:
    """True if project_id is a real Timetta UUID.

    Rejects empty values and placeholders like ``your_timetta_project_uuid``
    that otherwise reach Timetta and trigger a cryptic 400 «Entity cannot be null».
    """
    try:
        uuid.UUID(str(project_id))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


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


def _build_adapter(root: Path) -> TimettaAdapter:
    """Build TimettaAdapter from .env in root.

    Reads TIMETTA_TOKEN (and optionally TIMETTA_TAGS_DIR_ID) from .env,
    with environment variables taking precedence.

    Raises:
        SystemExit: if TIMETTA_TOKEN is not set.
    """
    env = load_env(root)
    token = env.get("TIMETTA_TOKEN") or os.environ.get("TIMETTA_TOKEN", "")
    if not token:
        raise RuntimeError("TIMETTA_TOKEN не задан (добавь в .env)")
    tags_dir_id = (
        env.get("TIMETTA_TAGS_DIR_ID")
        or os.environ.get("TIMETTA_TAGS_DIR_ID", "")
        or TimettaAdapter.DEFAULT_TAGS_DIR_ID
    )
    return TimettaAdapter(token=token, tags_dir_id=tags_dir_id)


def _active_project(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    registry: ProjectRegistry,
) -> ProjectConfig:
    """Return active ProjectConfig: dynamic selection > registry fallback.

    Checks context.chat_data["active_project_id"] first (set via /project inline
    keyboard). Falls back to registry.get_project(chat_id).
    """
    pid = (
        context.chat_data.get("active_project_id", "")
        if isinstance(context.chat_data, dict)
        else ""
    )
    if pid:
        logger.debug("[FIX] _active_project: dynamic project_id=%s chat=%s", pid, chat_id)
        return ProjectConfig(project_id=pid)
    return registry.get_project(chat_id)


def _run_submit(
    text: str,
    project: ProjectConfig,
    root: Path,
    project_path_override: Path | None = None,
) -> list[dict[str, Any]]:
    """Synchronous wrapper that builds adapter and calls submit_requirements."""
    adapter = _build_adapter(root)
    users = load_cached(root, "users", adapter.get_users)
    tags = load_cached(root, "tags", adapter.get_tags)
    effective_path = project_path_override if project_path_override is not None else project.project_path
    return submit_requirements(
        requirements=text,
        project_id=project.project_id,
        adapter=adapter,
        users=users,
        tags=tags,
        project_path=effective_path,
        root=root,
        sprint_id=project.sprint_id,
    )


async def _maybe_sync_vps(
    update: Any,
    project: ProjectConfig,
    cache_dir: Path,
) -> Path | None:
    """Sync VPS codebase if project.vps_remote is configured.

    Sends a status message to the user while syncing.

    Args:
        update: Telegram Update with an active message.
        project: ProjectConfig that may have vps_remote set.
        cache_dir: Base directory for cached codebases.

    Returns:
        Resolved local Path after sync, or None if no vps_remote.
    """
    if not project.vps_remote:
        return None
    await update.message.reply_text("🔄 Синхронизирую кодовую базу…")
    remote = project.vps_remote
    t0 = time.monotonic()
    local = await asyncio.to_thread(sync_codebase, remote, cache_dir)
    elapsed = time.monotonic() - t0
    logger.info(
        "[tg] vps_sync: %s → %s (%.1fs)", remote, local, elapsed
    )
    return local


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

    # ------------------------------------------------------------------
    # Inner helpers (capture config/registry via closure)
    # ------------------------------------------------------------------

    async def _fetch_project_content(
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        *,
        page: int = 0,
        refetch: bool = True,
    ) -> tuple[str, InlineKeyboardMarkup] | str:
        """Fetch Timetta projects and build a paginated inline selection keyboard.

        Returns (text, keyboard) on success, or an error string on failure.
        Side-effects: caches the ordered list in context.chat_data["_projects_list"]
        and {id: name} in "_project_cache". On page navigation pass refetch=False
        to reuse the cached list instead of hitting the API again.
        """
        chat_data = context.chat_data if isinstance(context.chat_data, dict) else {}

        projects: list[dict[str, str]] = chat_data.get("_projects_list", [])
        if refetch or not projects:
            try:
                adapter = _build_adapter(config.root)
            except Exception:
                return "❌ TIMETTA_TOKEN не задан. Добавьте его в .env."

            try:
                fetched: list[dict[str, Any]] = await asyncio.to_thread(adapter.get_projects)
            except Exception as exc:
                logger.exception("[tg] get_projects failed chat=%s", chat_id)
                return f"❌ Ошибка получения проектов: {exc}"

            if not fetched:
                return "ℹ️ Проекты не найдены в Timetta."

            projects = [{"id": p["id"], "name": p.get("name", p["id"])} for p in fetched]
            if isinstance(context.chat_data, dict):
                context.chat_data["_projects_list"] = projects
                context.chat_data["_project_cache"] = {p["id"]: p["name"] for p in projects}

        if not projects:
            return "ℹ️ Проекты не найдены в Timetta."

        total = len(projects)
        total_pages = (total + _API_PROJECTS_PAGE_SIZE - 1) // _API_PROJECTS_PAGE_SIZE
        page = max(0, min(page, total_pages - 1))
        page_items, has_prev, has_next = paginate(projects, page, _API_PROJECTS_PAGE_SIZE)

        active_id: str = chat_data.get("active_project_id", "")
        buttons: list[list[InlineKeyboardButton]] = []
        for p in page_items:
            pid = p["id"]
            name = p["name"]
            label = f"✅ {name}" if pid == active_id else name
            buttons.append([InlineKeyboardButton(label, callback_data=f"sel:{pid}")])

        nav: list[InlineKeyboardButton] = []
        if has_prev:
            nav.append(InlineKeyboardButton("← Назад", callback_data=f"apiproj_page:{page - 1}"))
        if has_next:
            nav.append(InlineKeyboardButton("Далее →", callback_data=f"apiproj_page:{page + 1}"))
        if nav:
            buttons.append(nav)

        cache: dict[str, str] = chat_data.get("_project_cache", {})
        header = f"📂 Активный: *{cache.get(active_id, active_id)}*\n\n" if active_id else ""
        note = f"\n\n_Стр. {page + 1}/{total_pages} · всего {total}_" if total_pages > 1 else ""
        logger.info("[tg] _fetch_project_content: %d projects chat=%s page=%d", total, chat_id, page)
        return f"{header}Выберите проект:{note}", InlineKeyboardMarkup(buttons)

    async def handle_apiproj_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle apiproj_page:N callback — navigate live Timetta-API project pages."""
        query = update.callback_query
        if query is None:
            return
        await query.answer()
        chat_id = update.effective_chat.id if update.effective_chat else 0
        data = query.data or ""
        try:
            page = int(data.split(":", 1)[1])
        except (IndexError, ValueError):
            logger.warning("[tg] apiproj_page: bad data=%r chat=%s", data, chat_id)
            return
        result = await _fetch_project_content(context, chat_id, page=page, refetch=False)
        if isinstance(result, str):
            await query.edit_message_text(result)
        else:
            text, keyboard = result
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        logger.info("[tg] apiproj_page: chat=%s page=%d", chat_id, page)

    def _build_favorites_content(
        context: ContextTypes.DEFAULT_TYPE,
    ) -> tuple[str, InlineKeyboardMarkup]:
        """Build favorites list text and inline keyboard."""
        favorites: list[dict[str, str]] = context.user_data.get("favorites", [])
        if not favorites:
            return (
                "⭐ Избранных проектов нет.\n\nДобавьте проект через /project.",
                InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 Открыть список проектов", callback_data="action:projects")],
                ]),
            )
        buttons: list[list[InlineKeyboardButton]] = []
        for fav in favorites:
            fid = fav["id"]
            fname = fav.get("name", fid)
            buttons.append([
                InlineKeyboardButton(f"⭐ {fname}", callback_data=f"sel:{fid}"),
                InlineKeyboardButton("✖", callback_data=f"fav_rm:{fid}"),
            ])
        buttons.append([InlineKeyboardButton("📋 Все проекты", callback_data="action:projects")])
        return "⭐ Избранные проекты:", InlineKeyboardMarkup(buttons)

    # ------------------------------------------------------------------
    # Pagination helpers
    # ------------------------------------------------------------------

    def _registry_items() -> list[dict[str, str]]:
        """Convert registry projects to item dicts for make_select_keyboard."""
        return [{"id": cfg.project_id, "name": key} for key, cfg in registry.list_projects()]

    async def cmd_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /projects — registry project list with pagination."""
        chat_id = update.effective_chat.id if update.effective_chat else 0
        logger.debug("[tg] command: /projects chat=%s", chat_id)
        items = _registry_items()
        if not items:
            await update.message.reply_text("ℹ️ Нет настроенных проектов.")
            return
        page = 0
        context.user_data["proj_page"] = page
        keyboard = make_select_keyboard("proj", items, "name", "id", page)
        total = len(items)
        await update.message.reply_text(
            f"📂 Выберите проект ({total} всего):",
            reply_markup=keyboard,
        )
        logger.info("[tg] proj: chat=%s total=%d page=%d", chat_id, total, page)

    async def handle_proj_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle proj_page:N callback — navigate registry project pages."""
        query = update.callback_query
        if query is None:
            return
        await query.answer()
        chat_id = update.effective_chat.id if update.effective_chat else 0
        data = query.data or ""
        try:
            page = int(data.split(":", 1)[1])
        except (IndexError, ValueError):
            logger.warning("[tg] proj_page: bad data=%r chat=%s", data, chat_id)
            return
        context.user_data["proj_page"] = page
        items = _registry_items()
        keyboard = make_select_keyboard("proj", items, "name", "id", page)
        await query.edit_message_reply_markup(reply_markup=keyboard)
        logger.info("[tg] proj_page: chat=%s page=%d", chat_id, page)

    async def handle_proj_sel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle proj_sel:UUID callback — activate a registry project."""
        query = update.callback_query
        if query is None:
            return
        await query.answer()
        chat_id = update.effective_chat.id if update.effective_chat else 0
        data = query.data or ""
        pid = data.split(":", 1)[1] if ":" in data else ""
        items = _registry_items()
        pname = next((item["name"] for item in items if item["id"] == pid), pid)
        if isinstance(context.chat_data, dict):
            context.chat_data["active_project_id"] = pid
        logger.info("[FIX] handle_proj_sel: chat=%s project_id=%s name=%s", chat_id, pid, pname)
        await query.edit_message_text(
            f"✅ Проект выбран: *{pname}*\n\nТеперь отправьте требования.",
            parse_mode="Markdown",
        )

    async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /tasks — paginated history of created tasks for this session."""
        chat_id = update.effective_chat.id if update.effective_chat else 0
        logger.debug("[tg] command: /tasks chat=%s", chat_id)
        history: list[dict[str, str]] = context.user_data.get("task_history", [])
        if not history:
            await update.message.reply_text(
                "ℹ️ История задач пуста. Отправьте требования для создания задач."
            )
            return
        page = 0
        context.user_data["task_page"] = page
        keyboard = make_select_keyboard("task", history, "summary", "id", page)
        total = len(history)
        await update.message.reply_text(
            f"📋 История задач ({total} всего):",
            reply_markup=keyboard,
        )
        logger.info("[tg] task_page: chat=%s page=%d total=%d", chat_id, page, total)

    async def handle_task_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle task_page:N callback — navigate task history pages."""
        query = update.callback_query
        if query is None:
            return
        await query.answer()
        chat_id = update.effective_chat.id if update.effective_chat else 0
        data = query.data or ""
        try:
            page = int(data.split(":", 1)[1])
        except (IndexError, ValueError):
            logger.warning("[tg] task_page: bad data=%r chat=%s", data, chat_id)
            return
        context.user_data["task_page"] = page
        history: list[dict[str, str]] = context.user_data.get("task_history", [])
        keyboard = make_select_keyboard("task", history, "summary", "id", page)
        await query.edit_message_reply_markup(reply_markup=keyboard)
        total = len(history)
        logger.info("[tg] task_page: chat=%s page=%d total=%d", chat_id, page, total)

    async def handle_task_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle task_sel:UUID callback — show task details."""
        query = update.callback_query
        if query is None:
            return
        await query.answer()
        chat_id = update.effective_chat.id if update.effective_chat else 0
        data = query.data or ""
        task_id = data.split(":", 1)[1] if ":" in data else ""
        history: list[dict[str, str]] = context.user_data.get("task_history", [])
        task = next((t for t in history if t.get("id") == task_id), None)
        if task is None:
            await query.edit_message_text("⚠️ Задача не найдена.")
            return
        summary = task.get("summary", "—")
        url = task.get("url", "")
        text = f"📌 *{summary}*"
        if url:
            text += f"\n\n🔗 {url}"
        logger.info("[tg] task_sel: chat=%s task_id=%s", chat_id, task_id)
        await query.edit_message_text(text, parse_mode="Markdown")

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

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
            project = _active_project(chat_id, context, registry)
        except KeyError:
            await update.message.reply_text(
                "❌ Проект не настроен. Выберите проект через /project."
            )
            return

        if not _is_valid_project_id(project.project_id):
            logger.warning(
                "[FIX] handle_text: invalid project_id=%r chat=%s",
                project.project_id, chat_id,
            )
            await update.message.reply_text(
                "❌ Проект не настроен. Выберите проект через /project."
            )
            return

        # VPS sync before submit (if configured)
        vps_cache = config.root / "cache" / "vps"
        project_path_override = await _maybe_sync_vps(update, project, vps_cache)

        await update.message.reply_text("⏳ Создаю задачи…")
        try:
            results = await asyncio.to_thread(
                _run_submit, text, project, config.root, project_path_override
            )
        except Exception as exc:
            logger.exception("[tg] submit failed: chat=%s", chat_id)
            await update.message.reply_text(f"❌ Ошибка создания задач: {exc}")
            return

        # Save last task ids for photo-without-caption flow
        context.user_data["last_task_ids"] = [r["id"] for r in results]
        # Accumulate task history for /tasks command
        history: list[dict[str, str]] = context.user_data.setdefault("task_history", [])
        for r in results:
            history.append({"summary": r.get("summary", ""), "url": r.get("url", ""), "id": r.get("id", "")})
        await update.message.reply_text(_format_results(results))

    async def _handle_media_message(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        file_id: str,
        filename: str,
        caption: str,
        media_label: str,
        tg_obj: Any,
    ) -> None:
        """Shared logic for photo and document handlers.

        If *caption* is non-empty: submits it as requirements, stores task IDs,
        then downloads and attaches the file to each created task.
        If *caption* is empty: attaches to ``context.user_data["last_task_ids"]``.

        Args:
            update: Telegram Update.
            context: Handler context (user_data used for last_task_ids).
            file_id: Telegram file_id (used as temp filename prefix).
            filename: Original filename (determines extension + temp path).
            caption: Message caption or empty string.
            media_label: Human-readable label for reply messages ("фото" / "файл").
            tg_obj: Telegram object with a ``.get_file()`` coroutine (PhotoSize or Document).
        """
        assert update.message is not None  # noqa: S101
        chat_id = update.effective_chat.id if update.effective_chat else 0
        task_ids: list[str] = []

        if caption.strip():
            try:
                project = _active_project(chat_id, context, registry)
            except KeyError:
                await update.message.reply_text(
                    "❌ Проект не настроен. Используйте /project для выбора проекта."
                )
                return

            if not _is_valid_project_id(project.project_id):
                logger.warning(
                    "[FIX] media: invalid project_id=%r chat=%s",
                    project.project_id, chat_id,
                )
                await update.message.reply_text(
                    "❌ Проект не настроен. Выберите проект через /project."
                )
                return

            vps_cache = config.root / "cache" / "vps"
            project_path_override = await _maybe_sync_vps(update, project, vps_cache)
            await update.message.reply_text("⏳ Создаю задачи…")
            try:
                results = await asyncio.to_thread(
                    _run_submit, caption, project, config.root, project_path_override
                )
            except Exception as exc:
                logger.exception("[tg] media submit failed: chat=%s", chat_id)
                await update.message.reply_text(f"❌ Ошибка создания задач: {exc}")
                return

            task_ids = [r["id"] for r in results]
            context.user_data["last_task_ids"] = task_ids
            media_history: list[dict[str, str]] = context.user_data.setdefault("task_history", [])
            for r in results:
                media_history.append({"summary": r.get("summary", ""), "url": r.get("url", ""), "id": r.get("id", "")})
            await update.message.reply_text(_format_results(results))
        else:
            task_ids = context.user_data.get("last_task_ids", [])
            if not task_ids:
                await update.message.reply_text(
                    "⚠️ Нет задач для прикрепления. Сначала отправьте текст с требованиями."
                )
                return

        # Download and attach
        suffix = Path(filename).suffix or ".bin"
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / f"{file_id}{suffix}"
            tg_file = await tg_obj.get_file()
            await tg_file.download_to_drive(tmp_path)

            file_size = tmp_path.stat().st_size
            logger.info("[tg] %s: chat=%s file_size=%d", media_label, chat_id, file_size)

            try:
                adapter = _build_adapter(config.root)
            except Exception as exc:
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

        n = "е" if attached == 1 else "ам"
        if attached:
            await update.message.reply_text(
                f"📎 {media_label.capitalize()} прикреплено к {attached} задач{n}."
            )
        else:
            await update.message.reply_text(
                f"⚠️ Не удалось прикрепить {media_label} (Timetta может не поддерживать вложения)."
            )

    async def handle_photo(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle photo messages: submit caption (if any) then attach photo."""
        assert update.message is not None  # noqa: S101
        chat_id = update.effective_chat.id if update.effective_chat else 0
        photo = update.message.photo[-1]
        logger.info("[tg] photo: chat=%s file_id=%s", chat_id, photo.file_id)
        await _handle_media_message(
            update, context,
            file_id=photo.file_id,
            filename=f"{photo.file_id}.jpg",
            caption=update.message.caption or "",
            media_label="фото",
            tg_obj=photo,
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
        logger.info("[tg] document: chat=%s file_name=%s", chat_id, doc.file_name)
        await _handle_media_message(
            update, context,
            file_id=doc.file_id,
            filename=doc.file_name or "file.bin",
            caption=update.message.caption or "",
            media_label="файл",
            tg_obj=doc,
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
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Выбрать проект", callback_data="action:projects")],
            [InlineKeyboardButton("⭐ Избранные проекты", callback_data="action:favorites")],
        ])
        await update.message.reply_text(
            "👋 Привет! Я помогу создавать задачи в Timetta.\n\n"
            "Просто напишите требования — я автоматически создам задачи.\n\n"
            "Команды:\n"
            "  /project — выбрать проект из Timetta\n"
            "  /favorites — избранные проекты\n\n"
            "Поддерживаю: текст, пересланные сообщения, фото и файлы.",
            reply_markup=keyboard,
        )

    async def cmd_project(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /project command — fetch projects from Timetta API as inline keyboard."""
        chat_id = update.effective_chat.id if update.effective_chat else 0
        logger.debug("[tg] command: /project chat=%s", chat_id)
        result = await _fetch_project_content(context, chat_id)
        if isinstance(result, str):
            await update.message.reply_text(result)
        else:
            text, keyboard = result
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

    async def cmd_favorites(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /favorites command — show favourite projects with quick-select buttons."""
        chat_id = update.effective_chat.id if update.effective_chat else 0
        logger.debug("[tg] command: /favorites chat=%s", chat_id)
        text, keyboard = _build_favorites_content(context)
        await update.message.reply_text(text, reply_markup=keyboard)
        logger.info(
            "[FIX] cmd_favorites: chat=%s favorites=%d",
            chat_id, len(context.user_data.get("favorites", [])),
        )

    async def handle_callback(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle inline keyboard button presses.

        Supported callback_data patterns:
          sel:{uuid}       — set active project for this chat
          fav_add:{uuid}   — add project to user favourites
          fav_rm:{uuid}    — remove project from user favourites
          action:projects  — show project selection list
          action:favorites — show favourites list
        """
        query = update.callback_query
        if query is None:
            return
        await query.answer()

        data = query.data or ""
        chat_id = update.effective_chat.id if update.effective_chat else 0
        logger.debug("[tg] callback: chat=%s data=%r", chat_id, data)

        if data.startswith("sel:"):
            pid = data[4:]
            cache: dict[str, str] = (
                context.chat_data.get("_project_cache", {})
                if isinstance(context.chat_data, dict)
                else {}
            )
            pname = cache.get(pid, pid)
            if isinstance(context.chat_data, dict):
                context.chat_data["active_project_id"] = pid
            logger.info("[FIX] handle_callback: sel chat=%s project_id=%s name=%s", chat_id, pid, pname)
            await query.edit_message_text(
                f"✅ Выбран проект: *{pname}*\n\nТеперь отправьте требования.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⭐ Добавить в избранные", callback_data=f"fav_add:{pid}")]
                ]),
                parse_mode="Markdown",
            )

        elif data.startswith("fav_add:"):
            pid = data[8:]
            cache = (
                context.chat_data.get("_project_cache", {})
                if isinstance(context.chat_data, dict)
                else {}
            )
            pname = cache.get(pid, pid)
            favorites: list[dict[str, str]] = context.user_data.setdefault("favorites", [])
            if not any(f["id"] == pid for f in favorites):
                favorites.append({"id": pid, "name": pname})
            logger.info("[FIX] handle_callback: fav_add chat=%s project_id=%s", chat_id, pid)
            await query.edit_message_text(
                f"⭐ Добавлено в избранные: *{pname}*", parse_mode="Markdown"
            )

        elif data.startswith("fav_rm:"):
            pid = data[7:]
            context.user_data["favorites"] = [
                f for f in context.user_data.get("favorites", []) if f["id"] != pid
            ]
            logger.info("[FIX] handle_callback: fav_rm chat=%s project_id=%s", chat_id, pid)
            await query.edit_message_text("✖ Проект удалён из избранных.")

        elif data == "action:projects":
            result = await _fetch_project_content(context, chat_id)
            if isinstance(result, str):
                await query.edit_message_text(result)
            else:
                text, keyboard = result
                await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

        elif data == "action:favorites":
            text, keyboard = _build_favorites_content(context)
            await query.edit_message_text(text, reply_markup=keyboard)

    # ------------------------------------------------------------------
    # Assemble handler list
    # ------------------------------------------------------------------
    return [
        CommandHandler("start", cmd_start),
        CommandHandler("project", cmd_project),
        CommandHandler("projects", cmd_projects),
        CommandHandler("favorites", cmd_favorites),
        CommandHandler("tasks", cmd_tasks),
        # Pattern-specific callbacks before the generic catch-all
        CallbackQueryHandler(handle_proj_page, pattern=r"^proj_page:"),
        CallbackQueryHandler(handle_proj_sel, pattern=r"^proj_sel:"),
        CallbackQueryHandler(handle_apiproj_page, pattern=r"^apiproj_page:"),
        CallbackQueryHandler(handle_task_page, pattern=r"^task_page:"),
        CallbackQueryHandler(handle_task_select, pattern=r"^task_sel:"),
        CallbackQueryHandler(handle_callback),
        MessageHandler(filters.PHOTO, handle_photo),
        MessageHandler(filters.Document.ALL, handle_document),
        # Text last: catches forwarded messages and plain text
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
    ]
