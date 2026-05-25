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
    _extract_forwarded_text,
    _format_results,
    _run_submit,
    make_handlers,
)
from tracker_assistant.telegram.config import BotConfig, ProjectConfig
from tracker_assistant.telegram.projects import ProjectRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_update(text="hello", chat_id=123, forward_date=None):
    msg = MagicMock()
    msg.text = text
    msg.caption = None
    msg.forward_date = forward_date
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
    return ctx


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
        msg.forward_date = None
        result = _extract_forwarded_text(msg)
        assert result is None

    def test_forwarded_returns_text(self):
        msg = MagicMock()
        msg.forward_date = datetime(2024, 1, 1)
        msg.text = "hello"
        msg.caption = None
        result = _extract_forwarded_text(msg)
        assert result == "hello"


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
        project = ProjectConfig(project_id="proj-1")
        registry = ProjectRegistry({f"chat_{chat_id}": project})
        return registry

    def _make_config(self, tmp_path):
        return BotConfig(token="tok", root=tmp_path, projects={})

    def test_handle_text_calls_submit(self, tmp_path):
        registry = self._make_registry_with_project(chat_id=123)
        config = self._make_config(tmp_path)
        handle_text = self._get_handle_text(registry, config)

        update = make_mock_update(text="create a login page", chat_id=123)
        context = make_mock_context()

        fake_results = [{"summary": "Login page", "url": "http://x", "id": "abc"}]

        async def run_test():
            with patch(
                "tracker_assistant.telegram.handlers._run_submit",
                return_value=fake_results,
            ) as mock_submit:
                with patch(
                    "tracker_assistant.telegram.handlers._maybe_sync_vps",
                    new=AsyncMock(return_value=None),
                ):
                    await handle_text(update, context)

            mock_submit.assert_called_once()
            call_kwargs = mock_submit.call_args
            assert call_kwargs[0][0] == "create a login page"

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


# ---------------------------------------------------------------------------
# handle_photo closure test
# ---------------------------------------------------------------------------


class TestHandlePhoto:
    def _get_handle_photo(self, registry, config):
        """Extract handle_photo handler (4th handler, index 3)."""
        handlers = make_handlers(registry, config)
        # CommandHandler x3, then PHOTO handler at index 3
        return handlers[3].callback

    def test_handle_photo_no_caption_attaches_to_last(self, tmp_path):
        project = ProjectConfig(project_id="proj-1")
        registry = ProjectRegistry({"chat_123": project})
        config = BotConfig(token="tok", root=tmp_path, projects={})
        handle_photo = self._get_handle_photo(registry, config)

        # Build update with a photo and no caption
        msg = MagicMock()
        msg.caption = None
        msg.forward_date = None
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
