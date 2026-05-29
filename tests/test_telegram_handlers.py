"""Tests for telegram/handlers.py helper functions and closures."""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tracker_assistant.telegram.handlers import (
    _active_project,
    _extract_forwarded_text,
    _format_preview,
    _format_results,
    make_handlers,
)
from tracker_assistant.telegram.config import BotConfig, ProjectConfig
from tracker_assistant.telegram.projects import ProjectRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_update(text="hello", chat_id=123, forward_origin=None):
    msg = MagicMock()
    msg.text = text
    msg.caption = None
    msg.forward_origin = forward_origin
    msg.reply_text = AsyncMock()
    msg.photo = None
    msg.document = None
    update = MagicMock()
    update.message = msg
    update.effective_chat = MagicMock()
    update.effective_chat.id = chat_id
    return update


def make_mock_context():
    ctx = MagicMock()
    ctx.user_data = {}
    ctx.chat_data = {}
    return ctx


def make_callback_update(data, chat_id=10):
    query = MagicMock()
    query.data = data
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.edit_message_reply_markup = AsyncMock()
    update = MagicMock()
    update.callback_query = query
    update.effective_chat = MagicMock()
    update.effective_chat.id = chat_id
    return update


# ---------------------------------------------------------------------------
# _format_results tests
# ---------------------------------------------------------------------------


class TestFormatResults:
    def test_format_results_empty(self):
        result = _format_results([])
        assert "не созданы" in result

    def test_format_results_single(self):
        result = _format_results([{"summary": "T", "url": "u", "id": "x"}])
        assert "✅ Создано 1 задача" in result

    def test_format_results_multiple(self):
        items = [
            {"summary": f"Task {i}", "url": f"url{i}", "id": f"id{i}"}
            for i in range(3)
        ]
        result = _format_results(items)
        assert "✅ Создано 3 задач" in result


# ---------------------------------------------------------------------------
# _extract_forwarded_text tests
# ---------------------------------------------------------------------------


class TestExtractForwardedText:
    def test_not_forwarded_returns_none(self):
        msg = MagicMock()
        msg.forward_origin = None
        result = _extract_forwarded_text(msg)
        assert result is None

    def test_forwarded_returns_text(self):
        msg = MagicMock()
        msg.forward_origin = MagicMock()  # any truthy MessageOrigin
        msg.text = "hello"
        msg.caption = None
        result = _extract_forwarded_text(msg)
        assert result == "hello"


# ---------------------------------------------------------------------------
# _active_project tests
# ---------------------------------------------------------------------------


class TestActiveProject:
    def _make_registry(self, chat_id=123):
        project = ProjectConfig(project_id="registry-proj")
        return ProjectRegistry({f"chat_{chat_id}": project})

    def test_returns_dynamic_project_when_set(self):
        registry = self._make_registry()
        ctx = make_mock_context()
        ctx.chat_data = {"active_project_id": "dynamic-uuid"}
        result = _active_project(123, ctx, registry)
        assert result.project_id == "dynamic-uuid"

    def test_falls_back_to_registry_when_no_dynamic(self):
        registry = self._make_registry(chat_id=123)
        ctx = make_mock_context()
        ctx.chat_data = {}
        result = _active_project(123, ctx, registry)
        assert result.project_id == "registry-proj"

    def test_falls_back_to_registry_when_chat_data_not_dict(self):
        registry = self._make_registry(chat_id=123)
        ctx = make_mock_context()
        ctx.chat_data = None
        result = _active_project(123, ctx, registry)
        assert result.project_id == "registry-proj"


# ---------------------------------------------------------------------------
# handle_text closure tests
# ---------------------------------------------------------------------------


class TestHandleText:
    def _get_handle_text(self, registry, config):
        """Extract handle_text handler (last handler in the list)."""
        handlers = make_handlers(registry, config)
        # Last handler is TEXT & ~COMMAND => handle_text
        return handlers[-1].callback

    def _make_registry_with_project(self, chat_id=123):
        project = ProjectConfig(project_id="11111111-1111-1111-1111-111111111111")
        registry = ProjectRegistry({f"chat_{chat_id}": project})
        return registry

    def _make_config(self, tmp_path):
        return BotConfig(token="tok", root=tmp_path, projects={})

    def test_handle_text_shows_preview_no_create(self, tmp_path):
        registry = self._make_registry_with_project(chat_id=123)
        config = self._make_config(tmp_path)
        handle_text = self._get_handle_text(registry, config)

        update = make_mock_update(text="create a login page", chat_id=123)
        context = make_mock_context()

        task_dicts = [{"summary": "Login page", "description": "d", "tags": [], "assignee": ""}]

        async def run_test():
            with patch(
                "tracker_assistant.telegram.handlers._run_generate",
                return_value=(task_dicts, [], []),
            ) as mock_generate, patch(
                "tracker_assistant.telegram.handlers._run_create",
            ) as mock_create, patch(
                "tracker_assistant.telegram.handlers._maybe_sync_vps",
                new=AsyncMock(return_value=None),
            ):
                await handle_text(update, context)

            # Generation happened, but nothing was created in Timetta.
            mock_generate.assert_called_once()
            assert mock_generate.call_args[0][0] == "create a login page"
            mock_create.assert_not_called()

            # Pending state stored for confirmation.
            pending = context.chat_data["pending_submit"]
            assert pending["task_dicts"] == task_dicts
            assert pending["requirements"] == "create a login page"
            assert pending["media"] is None

            # Reply carries the confirm/cancel keyboard.
            kwargs = update.message.reply_text.call_args.kwargs
            keyboard = kwargs["reply_markup"]
            callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
            assert "submit_ok:" in callbacks
            assert "submit_cancel:" in callbacks

        asyncio.run(run_test())

    def test_handle_text_uses_dynamic_project_from_chat_data(self, tmp_path):
        registry = ProjectRegistry({})  # no static projects
        config = self._make_config(tmp_path)
        handle_text = self._get_handle_text(registry, config)

        update = make_mock_update(text="build feature", chat_id=123)
        context = make_mock_context()
        context.chat_data = {"active_project_id": "22222222-2222-2222-2222-222222222222"}

        task_dicts = [{"summary": "Feature", "description": "", "tags": [], "assignee": ""}]

        async def run_test():
            with patch(
                "tracker_assistant.telegram.handlers._run_generate",
                return_value=(task_dicts, [], []),
            ) as mock_generate:
                with patch(
                    "tracker_assistant.telegram.handlers._maybe_sync_vps",
                    new=AsyncMock(return_value=None),
                ):
                    await handle_text(update, context)

            mock_generate.assert_called_once()
            project_arg = mock_generate.call_args[0][1]
            assert project_arg.project_id == "22222222-2222-2222-2222-222222222222"

        asyncio.run(run_test())

    def test_handle_text_no_project_error(self, tmp_path):
        # Registry with no matching project and no default — raises KeyError
        registry = ProjectRegistry({})
        config = self._make_config(tmp_path)
        handle_text = self._get_handle_text(registry, config)

        update = make_mock_update(text="do something", chat_id=999)
        context = make_mock_context()

        async def run_test():
            await handle_text(update, context)
            update.message.reply_text.assert_called_once()
            call_args = update.message.reply_text.call_args[0][0]
            assert "не настроен" in call_args

        asyncio.run(run_test())

    def test_handle_text_placeholder_project_id_rejected(self, tmp_path):
        # Placeholder/non-UUID project_id must not reach Timetta (would 400).
        project = ProjectConfig(project_id="your_timetta_project_uuid")
        registry = ProjectRegistry({"chat_123": project})
        config = self._make_config(tmp_path)
        handle_text = self._get_handle_text(registry, config)

        update = make_mock_update(text="create tasks", chat_id=123)
        context = make_mock_context()

        async def run_test():
            with patch(
                "tracker_assistant.telegram.handlers._run_generate",
            ) as mock_generate:
                await handle_text(update, context)

            mock_generate.assert_not_called()
            update.message.reply_text.assert_called_once()
            assert "не настроен" in update.message.reply_text.call_args[0][0]

        asyncio.run(run_test())


# ---------------------------------------------------------------------------
# Task review / confirmation / correction flow tests
# ---------------------------------------------------------------------------


class TestSubmitReviewFlow:
    def _make_config(self, tmp_path):
        return BotConfig(token="tok", root=tmp_path, projects={})

    def _make_registry(self, chat_id=123):
        project = ProjectConfig(project_id="11111111-1111-1111-1111-111111111111")
        return ProjectRegistry({f"chat_{chat_id}": project})

    def _get_callback(self, registry, config, pattern):
        from telegram.ext import CallbackQueryHandler
        handlers = make_handlers(registry, config)
        for h in handlers:
            pat = getattr(h, "pattern", None)
            if isinstance(h, CallbackQueryHandler) and pat is not None and pat.pattern == pattern:
                return h.callback
        raise AssertionError(f"handler {pattern} not found in handlers list")

    def _get_handle_text(self, registry, config):
        return make_handlers(registry, config)[-1].callback

    def test_submit_ok_creates_tasks(self, tmp_path):
        registry = self._make_registry()
        config = self._make_config(tmp_path)
        handle_submit_ok = self._get_callback(registry, config, "^submit_ok:")

        update = make_callback_update("submit_ok:", chat_id=123)
        context = make_mock_context()
        task_dicts = [{"summary": "T", "description": "", "tags": [], "assignee": ""}]
        context.chat_data = {"pending_submit": {
            "requirements": "req", "task_dicts": task_dicts,
            "project_id": "p", "project_path": None, "sprint_id": "", "media": None,
        }}
        results = [{"summary": "T", "url": "http://x", "id": "task-1"}]

        async def run_test():
            with patch(
                "tracker_assistant.telegram.handlers._run_create",
                return_value=results,
            ) as mock_create:
                await handle_submit_ok(update, context)

            mock_create.assert_called_once()
            assert mock_create.call_args[0][0] == task_dicts
            assert "pending_submit" not in context.chat_data
            assert context.user_data["last_task_ids"] == ["task-1"]
            last_text = update.callback_query.edit_message_text.call_args[0][0]
            assert "Создано" in last_text

        asyncio.run(run_test())

    def test_submit_ok_nothing_pending(self, tmp_path):
        registry = self._make_registry()
        config = self._make_config(tmp_path)
        handle_submit_ok = self._get_callback(registry, config, "^submit_ok:")

        update = make_callback_update("submit_ok:", chat_id=123)
        context = make_mock_context()

        async def run_test():
            with patch("tracker_assistant.telegram.handlers._run_create") as mock_create:
                await handle_submit_ok(update, context)
            mock_create.assert_not_called()
            assert "Нечего создавать" in update.callback_query.edit_message_text.call_args[0][0]

        asyncio.run(run_test())

    def test_submit_cancel_clears_pending(self, tmp_path):
        registry = self._make_registry()
        config = self._make_config(tmp_path)
        handle_submit_cancel = self._get_callback(registry, config, "^submit_cancel:")

        update = make_callback_update("submit_cancel:", chat_id=123)
        context = make_mock_context()
        context.chat_data = {"pending_submit": {"task_dicts": [], "media": None}}

        async def run_test():
            await handle_submit_cancel(update, context)
            assert "pending_submit" not in context.chat_data
            assert "Отменено" in update.callback_query.edit_message_text.call_args[0][0]

        asyncio.run(run_test())

    def test_text_while_pending_is_correction(self, tmp_path):
        registry = self._make_registry()
        config = self._make_config(tmp_path)
        handle_text = self._get_handle_text(registry, config)

        update = make_mock_update(text="make it shorter", chat_id=123)
        context = make_mock_context()
        old_dicts = [{"summary": "Old", "description": "", "tags": [], "assignee": ""}]
        context.chat_data = {"pending_submit": {
            "requirements": "original requirements", "task_dicts": old_dicts,
            "project_id": "11111111-1111-1111-1111-111111111111",
            "project_path": None, "sprint_id": "", "media": None,
        }}
        new_dicts = [{"summary": "New", "description": "", "tags": [], "assignee": ""}]

        async def run_test():
            with patch(
                "tracker_assistant.telegram.handlers._run_generate",
                return_value=(new_dicts, [], []),
            ) as mock_generate, patch(
                "tracker_assistant.telegram.handlers._run_create",
            ) as mock_create:
                await handle_text(update, context)

            mock_generate.assert_called_once()
            mock_create.assert_not_called()
            req_arg = mock_generate.call_args[0][0]
            assert "original requirements" in req_arg
            assert "make it shorter" in req_arg
            assert context.chat_data["pending_submit"]["task_dicts"] == new_dicts

        asyncio.run(run_test())

    def test_preview_format_detailed(self):
        users = [{"id": "u1", "displayName": "Иван Петров"}]
        tags = [{"id": "t1", "name": "Фронтенд"}]
        task_dicts = [{
            "summary": "Сделать форму логина",
            "description": "Очень длинное описание " * 20,
            "assignee": "u1",
            "tags": ["t1"],
        }]
        out = _format_preview(task_dicts, users, tags)
        assert "Проверь задачи (1)" in out
        assert "Сделать форму логина" in out
        assert "Иван Петров" in out
        assert "Фронтенд" in out
        assert "…" in out  # description truncated


# ---------------------------------------------------------------------------
# handle_photo closure test
# ---------------------------------------------------------------------------


class TestHandlePhoto:
    def _get_handle_photo(self, registry, config):
        """Extract handle_photo handler by locating the PHOTO MessageHandler."""
        from telegram.ext import MessageHandler, filters as tg_filters
        handlers = make_handlers(registry, config)
        for h in handlers:
            if isinstance(h, MessageHandler) and h.filters == tg_filters.PHOTO:
                return h.callback
        raise AssertionError("handle_photo not found in handlers list")

    def test_handle_photo_no_caption_attaches_to_last(self, tmp_path):
        project = ProjectConfig(project_id="proj-1")
        registry = ProjectRegistry({"chat_123": project})
        config = BotConfig(token="tok", root=tmp_path, projects={})
        handle_photo = self._get_handle_photo(registry, config)

        # Build update with a photo and no caption
        msg = MagicMock()
        msg.caption = None
        msg.forward_origin = None
        msg.reply_text = AsyncMock()

        # Mock the photo object
        photo_size = MagicMock()
        photo_size.file_id = "file123"
        msg.photo = [photo_size]  # list of PhotoSize; handler uses [-1]

        async def fake_download(path):
            Path(path).write_bytes(b"fake-image-data")

        tg_file = AsyncMock()
        tg_file.download_to_drive = fake_download
        photo_size.get_file = AsyncMock(return_value=tg_file)

        update = MagicMock()
        update.message = msg
        update.effective_chat = MagicMock()
        update.effective_chat.id = 123

        context = make_mock_context()
        context.user_data = {"last_task_ids": ["task-uuid-1"]}

        fake_adapter = MagicMock()
        fake_adapter.attach_file = MagicMock(return_value={"ok": True})

        async def run_test():
            with patch(
                "tracker_assistant.telegram.handlers._build_adapter",
                return_value=fake_adapter,
            ):
                await handle_photo(update, context)

            # attach_file should have been called with the task id
            fake_adapter.attach_file.assert_called_once()
            call_args = fake_adapter.attach_file.call_args[0]
            assert call_args[0] == "task-uuid-1"

        asyncio.run(run_test())


# ---------------------------------------------------------------------------
# cmd_project tests
# ---------------------------------------------------------------------------


class TestCmdProject:
    def _get_cmd_project(self, registry, config):
        handlers = make_handlers(registry, config)
        return handlers[1].callback  # index 1

    def _make_config(self, tmp_path):
        return BotConfig(token="tok", root=tmp_path, projects={})

    def test_shows_projects_from_api(self, tmp_path):
        registry = ProjectRegistry({})
        config = self._make_config(tmp_path)
        cmd_project = self._get_cmd_project(registry, config)

        update = make_mock_update(chat_id=10)
        context = make_mock_context()

        fake_projects = [
            {"id": "uuid-1", "name": "Alpha"},
            {"id": "uuid-2", "name": "Beta"},
        ]

        async def run_test():
            with patch("tracker_assistant.telegram.handlers._build_adapter") as mock_build:
                mock_adapter = MagicMock()
                mock_adapter.get_projects = MagicMock(return_value=fake_projects)
                mock_build.return_value = mock_adapter
                await cmd_project(update, context)

            update.message.reply_text.assert_called_once()
            # Project cache should be populated
            assert context.chat_data.get("_project_cache") == {"uuid-1": "Alpha", "uuid-2": "Beta"}

        asyncio.run(run_test())

    def test_error_when_no_token(self, tmp_path):
        registry = ProjectRegistry({})
        config = self._make_config(tmp_path)
        cmd_project = self._get_cmd_project(registry, config)

        update = make_mock_update(chat_id=10)
        context = make_mock_context()

        async def run_test():
            with patch(
                "tracker_assistant.telegram.handlers._build_adapter",
                side_effect=RuntimeError("no token"),
            ):
                await cmd_project(update, context)

            update.message.reply_text.assert_called_once()
            msg = update.message.reply_text.call_args[0][0]
            assert "TIMETTA_TOKEN" in msg

        asyncio.run(run_test())

    def _get_apiproj_page(self, registry, config):
        from telegram.ext import CallbackQueryHandler
        handlers = make_handlers(registry, config)
        for h in handlers:
            pat = getattr(h, "pattern", None)
            if isinstance(h, CallbackQueryHandler) and pat is not None and pat.pattern == "^apiproj_page:":
                return h.callback
        raise AssertionError("handle_apiproj_page not found in handlers list")

    def test_paginates_many_projects(self, tmp_path):
        registry = ProjectRegistry({})
        config = self._make_config(tmp_path)
        cmd_project = self._get_cmd_project(registry, config)

        update = make_mock_update(chat_id=10)
        context = make_mock_context()
        fake_projects = [{"id": f"uuid-{i}", "name": f"P{i}"} for i in range(20)]

        async def run_test():
            with patch("tracker_assistant.telegram.handlers._build_adapter") as mock_build:
                mock_adapter = MagicMock()
                mock_adapter.get_projects = MagicMock(return_value=fake_projects)
                mock_build.return_value = mock_adapter
                await cmd_project(update, context)

            # Full ordered list cached for page navigation
            assert len(context.chat_data["_projects_list"]) == 20
            kb = update.message.reply_text.call_args.kwargs["reply_markup"]
            rows = kb.inline_keyboard
            # 8 item rows (page size) + 1 navigation row
            assert len(rows) == 9
            nav_labels = [b.text for b in rows[-1]]
            assert "Далее →" in nav_labels
            assert "← Назад" not in nav_labels  # first page has no prev

        asyncio.run(run_test())

    def test_apiproj_page_navigates_without_refetch(self, tmp_path):
        registry = ProjectRegistry({})
        config = self._make_config(tmp_path)
        handle_apiproj_page = self._get_apiproj_page(registry, config)

        update = make_callback_update("apiproj_page:1", chat_id=10)
        context = make_mock_context()
        projects = [{"id": f"uuid-{i}", "name": f"P{i}"} for i in range(20)]
        context.chat_data["_projects_list"] = projects
        context.chat_data["_project_cache"] = {p["id"]: p["name"] for p in projects}

        async def run_test():
            with patch("tracker_assistant.telegram.handlers._build_adapter") as mock_build:
                await handle_apiproj_page(update, context)
                mock_build.assert_not_called()  # cached list reused, no API hit

            update.callback_query.edit_message_text.assert_called_once()
            kb = update.callback_query.edit_message_text.call_args.kwargs["reply_markup"]
            nav_labels = [b.text for b in kb.inline_keyboard[-1]]
            # middle page of 3 (20 items / 8) → both nav directions present
            assert "← Назад" in nav_labels
            assert "Далее →" in nav_labels

        asyncio.run(run_test())


# ---------------------------------------------------------------------------
# cmd_favorites tests
# ---------------------------------------------------------------------------


class TestCmdFavorites:
    def _get_cmd_favorites(self, registry, config):
        from telegram.ext import CommandHandler as CH
        handlers = make_handlers(registry, config)
        for h in handlers:
            if isinstance(h, CH) and "favorites" in h.commands:
                return h.callback
        raise AssertionError("cmd_favorites not found in handlers list")

    def _make_config(self, tmp_path):
        return BotConfig(token="tok", root=tmp_path, projects={})

    def test_empty_favorites_shows_hint(self, tmp_path):
        registry = ProjectRegistry({})
        config = self._make_config(tmp_path)
        cmd_favorites = self._get_cmd_favorites(registry, config)

        update = make_mock_update(chat_id=5)
        context = make_mock_context()
        context.user_data = {}

        async def run_test():
            await cmd_favorites(update, context)
            update.message.reply_text.assert_called_once()
            msg = update.message.reply_text.call_args[0][0]
            assert "нет" in msg

        asyncio.run(run_test())

    def test_with_favorites_shows_buttons(self, tmp_path):
        registry = ProjectRegistry({})
        config = self._make_config(tmp_path)
        cmd_favorites = self._get_cmd_favorites(registry, config)

        update = make_mock_update(chat_id=5)
        context = make_mock_context()
        context.user_data = {"favorites": [{"id": "fav-uuid", "name": "MyProject"}]}

        async def run_test():
            await cmd_favorites(update, context)
            update.message.reply_text.assert_called_once()
            _, kwargs = update.message.reply_text.call_args
            keyboard = kwargs.get("reply_markup")
            assert keyboard is not None
            # Inline keyboard should contain the favourite project
            labels = [btn.text for row in keyboard.inline_keyboard for btn in row]
            assert any("MyProject" in label for label in labels)

        asyncio.run(run_test())


# ---------------------------------------------------------------------------
# handle_callback tests
# ---------------------------------------------------------------------------


class TestCallbackHandler:
    def _get_handle_callback(self, registry, config):
        from telegram.ext import CallbackQueryHandler as CQH
        handlers = make_handlers(registry, config)
        # Return the generic (no-pattern) CallbackQueryHandler
        for h in handlers:
            if isinstance(h, CQH) and h.pattern is None:
                return h.callback
        raise AssertionError("generic handle_callback not found in handlers list")

    def _make_config(self, tmp_path):
        return BotConfig(token="tok", root=tmp_path, projects={})

    def _make_callback_update(self, data, chat_id=10):
        query = MagicMock()
        query.data = data
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update = MagicMock()
        update.callback_query = query
        update.effective_chat = MagicMock()
        update.effective_chat.id = chat_id
        return update, query

    def test_sel_sets_active_project(self, tmp_path):
        registry = ProjectRegistry({})
        config = self._make_config(tmp_path)
        handle_callback = self._get_handle_callback(registry, config)

        update, query = self._make_callback_update("sel:test-project-uuid")
        context = make_mock_context()
        context.chat_data = {"_project_cache": {"test-project-uuid": "Test Project"}}

        async def run_test():
            await handle_callback(update, context)
            assert context.chat_data["active_project_id"] == "test-project-uuid"
            query.answer.assert_called_once()
            query.edit_message_text.assert_called_once()
            msg = query.edit_message_text.call_args[0][0]
            assert "Test Project" in msg

        asyncio.run(run_test())

    def test_fav_add_appends_to_favorites(self, tmp_path):
        registry = ProjectRegistry({})
        config = self._make_config(tmp_path)
        handle_callback = self._get_handle_callback(registry, config)

        pid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        update, query = self._make_callback_update(f"fav_add:{pid}")
        context = make_mock_context()
        context.chat_data = {"_project_cache": {pid: "Cool Project"}}

        async def run_test():
            await handle_callback(update, context)
            favs = context.user_data.get("favorites", [])
            assert len(favs) == 1
            assert favs[0]["id"] == pid
            assert favs[0]["name"] == "Cool Project"

        asyncio.run(run_test())

    def test_fav_add_no_duplicates(self, tmp_path):
        registry = ProjectRegistry({})
        config = self._make_config(tmp_path)
        handle_callback = self._get_handle_callback(registry, config)

        pid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        update, query = self._make_callback_update(f"fav_add:{pid}")
        context = make_mock_context()
        context.chat_data = {"_project_cache": {pid: "Cool"}}
        context.user_data = {"favorites": [{"id": pid, "name": "Cool"}]}

        async def run_test():
            await handle_callback(update, context)
            assert len(context.user_data["favorites"]) == 1  # no duplicate

        asyncio.run(run_test())

    def test_fav_rm_removes_from_favorites(self, tmp_path):
        registry = ProjectRegistry({})
        config = self._make_config(tmp_path)
        handle_callback = self._get_handle_callback(registry, config)

        pid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        update, query = self._make_callback_update(f"fav_rm:{pid}")
        context = make_mock_context()
        context.user_data = {
            "favorites": [
                {"id": pid, "name": "Remove Me"},
                {"id": "other-uuid", "name": "Keep Me"},
            ]
        }

        async def run_test():
            await handle_callback(update, context)
            favs = context.user_data.get("favorites", [])
            assert len(favs) == 1
            assert favs[0]["id"] == "other-uuid"

        asyncio.run(run_test())
