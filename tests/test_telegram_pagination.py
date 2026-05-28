"""Tests for telegram/pagination.py utility."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tracker_assistant.telegram.pagination import (
    make_nav_keyboard,
    make_select_keyboard,
    paginate,
)


# ---------------------------------------------------------------------------
# paginate
# ---------------------------------------------------------------------------


def test_paginate_first_page():
    items = list(range(12))
    page_items, has_prev, has_next = paginate(items, page=0)
    assert page_items == [0, 1, 2, 3, 4]
    assert has_prev is False
    assert has_next is True


def test_paginate_middle_page():
    items = list(range(12))
    page_items, has_prev, has_next = paginate(items, page=1)
    assert page_items == [5, 6, 7, 8, 9]
    assert has_prev is True
    assert has_next is True


def test_paginate_last_page():
    items = list(range(12))
    page_items, has_prev, has_next = paginate(items, page=2)
    assert page_items == [10, 11]
    assert has_prev is True
    assert has_next is False


def test_paginate_empty():
    page_items, has_prev, has_next = paginate([], page=0)
    assert page_items == []
    assert has_prev is False
    assert has_next is False


def test_paginate_single_page():
    items = [1, 2, 3]
    page_items, has_prev, has_next = paginate(items, page=0)
    assert page_items == [1, 2, 3]
    assert has_prev is False
    assert has_next is False


def test_paginate_clamps_page_below_zero():
    items = list(range(10))
    page_items, has_prev, has_next = paginate(items, page=-5)
    assert page_items == [0, 1, 2, 3, 4]
    assert has_prev is False


def test_paginate_clamps_page_above_max():
    items = list(range(7))
    page_items, has_prev, has_next = paginate(items, page=99)
    assert page_items == [5, 6]
    assert has_next is False


# ---------------------------------------------------------------------------
# make_nav_keyboard
# ---------------------------------------------------------------------------


def test_make_nav_keyboard_both_dirs():
    kb = make_nav_keyboard("x", page=2, has_prev=True, has_next=True)
    row = kb.inline_keyboard[0]
    assert len(row) == 2
    assert row[0].text == "← Назад"
    assert row[0].callback_data == "x_page:1"
    assert row[1].text == "Далее →"
    assert row[1].callback_data == "x_page:3"


def test_make_nav_keyboard_first_page():
    kb = make_nav_keyboard("x", page=0, has_prev=False, has_next=True)
    row = kb.inline_keyboard[0]
    assert len(row) == 1
    assert row[0].text == "Далее →"
    assert row[0].callback_data == "x_page:1"


def test_make_nav_keyboard_last_page():
    kb = make_nav_keyboard("x", page=3, has_prev=True, has_next=False)
    row = kb.inline_keyboard[0]
    assert len(row) == 1
    assert row[0].text == "← Назад"
    assert row[0].callback_data == "x_page:2"


def test_make_nav_keyboard_no_nav():
    kb = make_nav_keyboard("x", page=0, has_prev=False, has_next=False)
    assert len(kb.inline_keyboard) == 0


# ---------------------------------------------------------------------------
# make_select_keyboard
# ---------------------------------------------------------------------------


def _items(n: int) -> list[dict[str, str]]:
    return [{"id": str(i), "name": f"Item {i}"} for i in range(n)]


def test_make_select_keyboard_items_and_nav():
    items = _items(7)
    kb = make_select_keyboard("p", items, label_key="name", id_key="id", page=0)
    rows = kb.inline_keyboard
    # 5 item rows + 1 nav row
    assert len(rows) == 6
    # Each item row has one button
    for row in rows[:5]:
        assert len(row) == 1
    # Nav row has one button (Далее → only, since page 0)
    nav_row = rows[5]
    assert len(nav_row) == 1
    assert nav_row[0].text == "Далее →"


def test_make_select_keyboard_item_callback_format():
    items = [{"id": "abc-123", "name": "My Project"}]
    kb = make_select_keyboard("proj", items, "name", "id", page=0)
    btn = kb.inline_keyboard[0][0]
    assert btn.text == "My Project"
    assert btn.callback_data == "proj_sel:abc-123"


def test_make_select_keyboard_empty_items():
    kb = make_select_keyboard("p", [], "name", "id", page=0)
    assert len(kb.inline_keyboard) == 0


def test_make_select_keyboard_single_page_no_nav():
    items = _items(3)
    kb = make_select_keyboard("p", items, "name", "id", page=0)
    rows = kb.inline_keyboard
    # 3 item rows, no nav row
    assert len(rows) == 3
