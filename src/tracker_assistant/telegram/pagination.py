from __future__ import annotations

"""Utility for paginating Telegram inline keyboards."""

import logging
import math
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


def paginate(
    items: list,
    page: int,
    page_size: int = 5,
) -> tuple[list, bool, bool]:
    """Slice *items* to a single page.

    Returns:
        (page_items, has_prev, has_next)
    """
    if not items:
        logger.debug("paginate: empty items list")
        return [], False, False

    total_pages = math.ceil(len(items) / page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    end = start + page_size
    page_items = items[start:end]
    has_prev = page > 0
    has_next = end < len(items)
    logger.debug("paginate: page=%d/%d items=%d", page, total_pages, len(page_items))
    return page_items, has_prev, has_next


def make_nav_keyboard(
    prefix: str,
    page: int,
    has_prev: bool,
    has_next: bool,
) -> InlineKeyboardMarkup:
    """Build a navigation-only row (← Назад / Далее →).

    Buttons that don't apply are omitted.
    """
    nav: list[InlineKeyboardButton] = []
    if has_prev:
        nav.append(InlineKeyboardButton("← Назад", callback_data=f"{prefix}_page:{page - 1}"))
    if has_next:
        nav.append(InlineKeyboardButton("Далее →", callback_data=f"{prefix}_page:{page + 1}"))
    return InlineKeyboardMarkup([nav] if nav else [])


def make_select_keyboard(
    prefix: str,
    items: list[dict[str, Any]],
    label_key: str,
    id_key: str,
    page: int,
    page_size: int = 5,
) -> InlineKeyboardMarkup:
    """Build a selection keyboard: one row per item + navigation row at bottom."""
    page_items, has_prev, has_next = paginate(items, page, page_size)

    buttons: list[list[InlineKeyboardButton]] = []
    for item in page_items:
        label = str(item.get(label_key, item.get(id_key, "?")))
        item_id = str(item.get(id_key, ""))
        buttons.append([InlineKeyboardButton(label, callback_data=f"{prefix}_sel:{item_id}")])

    nav: list[InlineKeyboardButton] = []
    if has_prev:
        nav.append(InlineKeyboardButton("← Назад", callback_data=f"{prefix}_page:{page - 1}"))
    if has_next:
        nav.append(InlineKeyboardButton("Далее →", callback_data=f"{prefix}_page:{page + 1}"))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(buttons)
