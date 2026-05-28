# Telegram Bot: пагинация списков (проекты + задачи)

**Создан:** 2026-05-25  
**Режим:** fast  
**Зависимость:** реализация `telegram-bot-interface.md` (tasks 1–10)

## Настройки

- **Тестирование:** да
- **Логирование:** verbose (DEBUG)
- **Docs:** нет

## Контекст

Пагинация нужна в двух местах:
- **Выбор проекта** — при мульти-проектном режиме список проектов выводится inline-кнопками, по 5 на страницу
- **`/tasks`** — история созданных задач в сессии, по 5 на страницу

Оба случая используют одну утилиту `telegram/pagination.py`.  
Callback data формат: `{prefix}_page:{n}` (листать), `{prefix}_sel:{id}` (выбрать).

## Задачи

- [x] 1. **`telegram/pagination.py`** — утилита пагинации
  - `paginate(items: list, page: int, page_size: int = 5) -> tuple[list, bool, bool]`  
    возвращает `(page_items, has_prev, has_next)`
  - `make_nav_keyboard(prefix: str, page: int, has_prev: bool, has_next: bool) -> InlineKeyboardMarkup`  
    кнопки `← Назад` / `Далее →` с callback `{prefix}_page:{n}`; отсутствующие направления не рисуются
  - `make_select_keyboard(prefix: str, items: list[dict], label_key: str, id_key: str, page: int, page_size: int = 5) -> InlineKeyboardMarkup`  
    строки-кнопки `{item[label_key]}` с callback `{prefix}_sel:{item[id_key]}` + навигация внизу
  - Лог: `logger.debug("paginate: page=%d/%d items=%d", page, total_pages, len(page_items))`
  - Файл: `src/tracker_assistant/telegram/pagination.py`

- [x] 2. **Пагинация списка проектов** — обновить `handlers.py` + `bot.py`
  - Новая команда `/projects` → показать страницу проектов из `registry.list_projects()`
  - `_handle_projects_command(update, context)` — отправляет `make_select_keyboard("proj", ...)`
  - `_handle_proj_page(update, context)` — `CallbackQueryHandler(pattern=r"^proj_page:")`  
    обновляет `context.user_data["proj_page"]`, редактирует сообщение через `query.edit_message_reply_markup`
  - `_handle_proj_select(update, context)` — `CallbackQueryHandler(pattern=r"^proj_sel:")`  
    сохраняет `context.user_data["active_project_id"]`, отвечает `✅ Проект выбран: {name}`
  - Зарегистрировать в `bot.py`: `CommandHandler("projects", ...)`, два `CallbackQueryHandler`
  - Лог: `logger.info("[tg] proj_page: chat=%s page=%d", chat_id, page)`
  - Файлы: `src/tracker_assistant/telegram/handlers.py`, `src/tracker_assistant/telegram/bot.py`

- [x] 3. **Пагинация `/tasks`** — обновить `handlers.py`
  - Хранить полную историю: `context.user_data["task_history"]` — список всех созданных задач за сессию  
    (каждая запись: `{"summary": "...", "url": "...", "id": "..."}`)
  - Обновить `_handle_tasks_command` (задача 7 в telegram-bot-interface.md):  
    вместо плоского списка — `make_select_keyboard("task", task_history, "summary", "id", page)`
  - `_handle_task_page(update, context)` — `CallbackQueryHandler(pattern=r"^task_page:")`  
    редактирует сообщение через `query.edit_message_text`
  - `_handle_task_select(update, context)` — `CallbackQueryHandler(pattern=r"^task_sel:")`  
    показывает детали задачи: summary + URL
  - Лог: `logger.info("[tg] task_page: chat=%s page=%d total=%d", chat_id, page, len(history))`
  - Файл: `src/tracker_assistant/telegram/handlers.py`

- [x] 4. **Тесты** — `tests/test_telegram_pagination.py`
  - `test_paginate_first_page` — 12 items, page=0 → 5 items, has_prev=False, has_next=True
  - `test_paginate_middle_page` — 12 items, page=1 → 5 items, has_prev=True, has_next=True
  - `test_paginate_last_page` — 12 items, page=2 → 2 items, has_prev=True, has_next=False
  - `test_paginate_empty` — [] → [], False, False
  - `test_paginate_single_page` — 3 items, page=0 → 3 items, False, False
  - `test_make_nav_keyboard_both_dirs` — has_prev=True, has_next=True → 2 кнопки в ряду
  - `test_make_nav_keyboard_first_page` — has_prev=False → только кнопка «Далее →»
  - `test_make_nav_keyboard_last_page` — has_next=False → только кнопка «← Назад»
  - `test_make_select_keyboard_items_and_nav` — 7 items, page=0 → 5 item-кнопок + nav-ряд
  - Файл: `tests/test_telegram_pagination.py`

## Commit Plan

| После задачи | Коммит |
|---|---|
| 1 | `feat(telegram): add pagination utility module` |
| 3 | `feat(telegram): add paginated projects and tasks lists` |
| 4 | `test(telegram): add tests for pagination` |
