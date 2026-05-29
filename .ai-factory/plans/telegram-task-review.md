# Telegram: ревью задач перед выгрузкой в Timetta

**Ветка:** нет (create_branches: false)
**Создан:** 2026-05-29
**Описание:** Изменить пайплайн submit в Telegram-боте: после получения требований
задачи сначала формируются по шаблону (только генерация через claude) и
отправляются пользователю на проверку постановки и декомпозиции. После
подтверждения — выгружаются в Timetta. Если пользователь не подтверждает —
присылает свободным текстом правки, и задачи перегенерируются.

## Настройки

- **Тестирование:** да
- **Логирование:** verbose (DEBUG)
- **Docs:** да — обязательный checkpoint через `/aif-docs` после завершения

## Roadmap Linkage

Milestone: "none"
Rationale: Skipped by user

## Флоу (до → после)

```
ДО:
  требования → submit_requirements (claude + создание в Timetta разом) → ответ с URL

ПОСЛЕ:
  требования → generate_tasks (только claude) → превью (подробное) + [✅ Создать] [❌ Отмена]
    ├─ ✅ Создать  → create_tasks (выгрузка в Timetta) → ответ с URL + attach (если было фото)
    ├─ ❌ Отмена   → очистка pending, "Отменено"
    └─ текст (пока ждём подтверждения) → ПРАВКА → generate_tasks(требования + правка)
                                         → обновлённое превью
```

**Состояние** в `context.chat_data["pending_submit"]`:
```python
{
  "requirements": str,         # исходный текст (для регенерации с правкой)
  "task_dicts":   list[dict],  # подготовленные задачи (превью + основа для создания)
  "project_id":   str,
  "project_path": str | None,
  "sprint_id":    str,
  "media": {"file_id": str, "filename": str, "label": str} | None,  # фото+подпись
}
```
Одно pending на чат; новая генерация перезаписывает. Наличие `pending_submit`
переводит чат в режим «ждём подтверждения».

## Архитектура изменений

**`submit/service.py`** — разбить `submit_requirements` на две функции:
- `generate_tasks(...) -> list[dict]` — стек-анализ + `build_prompt` + `call_claude_list`
  + нормализация (`project_id`, `task_type`, `sprintId`). НИКАКИХ вызовов Timetta.
  Возвращает подготовленные task_dict'ы (с сырыми `tags`/`assignee` внутри — для превью и создания).
- `create_tasks(task_dicts, ...) -> list[dict]` — текущий цикл создания: `resolve_tags`,
  `create_task`, `update_task` (теги+исполнитель), сбор результатов с URL.
- `submit_requirements(...)` — тонкая обёртка `create_tasks(generate_tasks(...))`,
  чтобы CLI (`task-submit`) и существующие тесты не сломались.

**`telegram/handlers.py`** — превью/подтверждение поверх существующих inline/callback хендлеров:
- `_run_generate(...)` / `_run_create(...)` — синхронные обёртки для `asyncio.to_thread`.
- `_format_preview(task_dicts, users, tags)` — подробное превью (см. ниже).
- callback'и `submit_ok:` / `submit_cancel:` (отдельные паттерн-хендлеры до общего `handle_callback`).
- режим правок: в `handle_text`, если есть `pending_submit` → текст трактуется как правка.

**Формат подробного превью** (на каждую задачу):
```
1. <summary>
   <описание, обрезано до ~150 симв>
   👤 <исполнитель: displayName или "—">   🏷 <теги: имена через запятую или "—">
```
Заголовок: `📋 Проверь задачи (N). Всё ок — нажми «Создать», или пришли правки текстом.`

## Задачи

### Фаза 1 — Разбиение submit-сервиса

- [x] 1. **Разбить `submit_requirements`** на `generate_tasks` + `create_tasks`
  - `generate_tasks(requirements, project_id, project_path, root, *, tags, users, sprint_id, default_task_type=DEFAULT_TASK_TYPE) -> list[dict]`:
    - стек-анализ (`scan_project_stack`/`empty_stack` + `build_stack_context`)
    - `build_prompt` + `call_claude_list`
    - нормализация каждого dict: `setdefault("project_id", ...)`, `task_type` ← default если пусто, `extra["sprintId"]` если есть sprint_id
    - вернуть список dict'ов (теги/assignee остаются внутри)
  - `create_tasks(task_dicts, *, adapter, tags, root) -> list[dict]`:
    - перенести текущий цикл создания из `submit_requirements` (pop tags → `resolve_tags`, `create_task`, `update_task`, сбор `results` с url)
  - `submit_requirements(...)` → `create_tasks(generate_tasks(...), adapter=..., tags=..., root=...)` (та же сигнатура, тот же результат)
  - Лог: `logger.info("generate_tasks: %d задач(и) сгенерировано", n)`, `logger.info("create_tasks: %d создано", n)`
  - Экспорт `generate_tasks`, `create_tasks` в `submit/__init__.py`
  - Файлы: `src/tracker_assistant/submit/service.py`, `src/tracker_assistant/submit/__init__.py`

> **💾 Commit 1** (после задачи 1): `refactor(submit): split generate_tasks and create_tasks`

---

### Фаза 2 — Telegram: превью, подтверждение, правки

- [x] 2. **Генерация + превью в `handle_text`** (вместо прямого создания)
  - Добавить `_run_generate(text, project, root, project_path_override) -> list[dict]` (build adapter, `load_cached` users/tags, `generate_tasks`)
  - Добавить `_format_preview(task_dicts, users, tags) -> str` — подробное превью (см. раздел «Формат»); маппинг assignee→displayName по `users`, тегов→имена по `tags`, fallback на сырое значение; описание обрезать до ~150 симв
  - В `handle_text`: после валидации project_id и VPS-sync — вместо `_run_submit` вызвать `_run_generate` в `asyncio.to_thread`, при пустом результате — `⚠️ Задачи не сгенерированы`, иначе сохранить `pending_submit` в `chat_data` и отправить превью + клавиатуру `[✅ Создать][❌ Отмена]` (callback `submit_ok:` / `submit_cancel:`)
  - Сообщение прогресса: `⏳ Формирую задачи…` (вместо `Создаю задачи…`)
  - Лог: `logger.info("[tg] generate: chat=%s tasks=%d", chat_id, len(task_dicts))`
  - Файл: `src/tracker_assistant/telegram/handlers.py`

- [x] 3. **Подтверждение/отмена** — callback-хендлеры
  - `_run_create(task_dicts, project, root) -> list[dict]` (build adapter, `load_cached` tags, `create_tasks`)
  - `handle_submit_ok`: достать `pending_submit`; если нет → `⚠️ Нечего создавать`; иначе `⏳ Выгружаю в Timetta…`, `_run_create` в потоке, `_format_results`, сохранить `last_task_ids`/`task_history`, очистить `pending_submit`. Если в pending есть `media` → после создания скачать файл по `file_id` и прикрепить к задачам (вынести download+attach из `_handle_media_message` в общий хелпер `_attach_to_tasks`)
  - `handle_submit_cancel`: очистить `pending_submit`, `edit_message_text("❌ Отменено")`
  - Ошибки `_run_create` ловить `except Exception` → `❌ Ошибка создания задач: <exc>` (как в текущем коде)
  - Зарегистрировать `CallbackQueryHandler(handle_submit_ok, pattern=r"^submit_ok:")` и `..._cancel` ДО общего `handle_callback`
  - Лог: `logger.info("[tg] submit_ok: chat=%s created=%d", chat_id, len(results))`
  - Файл: `src/tracker_assistant/telegram/handlers.py`

- [x] 4. **Правки свободным текстом** — в начале `handle_text`
  - Если `chat_data.get("pending_submit")` существует и пришёл обычный текст → это правка:
    - `requirements = pending["requirements"] + "\n\nПравки от пользователя:\n" + correction`
    - перегенерировать через `_run_generate` (использовать сохранённые project/project_path), обновить `pending_submit` (новые `task_dicts`, обновлённый `requirements`), отправить новое превью + клавиатуру
    - сообщение: `✏️ Учёл правки, пересобираю…`
  - Лог: `logger.info("[tg] correction: chat=%s len=%d", chat_id, len(correction))`
  - Файл: `src/tracker_assistant/telegram/handlers.py`

- [x] 5. **Фото+подпись через превью**
  - В `_handle_media_message` (ветка `caption.strip()`): вместо немедленного создания — `_run_generate(caption)`, сохранить `pending_submit` с `media={"file_id", "filename", "label"}`, показать превью + кнопки (как текст)
  - Создание и прикрепление выполняются в `handle_submit_ok` (общий хелпер `_attach_to_tasks(adapter, task_ids, file_id, filename, label, get_file_coro)` — скачивание во временную директорию + `attach_file`)
  - Фото БЕЗ подписи (прикрепление к `last_task_ids`) — без изменений
  - Лог: `logger.info("[tg] media generate: chat=%s label=%s", chat_id, label)`
  - Файл: `src/tracker_assistant/telegram/handlers.py`

> **💾 Commit 2** (после задачи 5): `feat(telegram): review tasks before uploading to Timetta`

---

### Фаза 3 — Тесты

- [x] 6. **Тесты разбиения сервиса** — `tests/test_submit_task.py`
  - `test_generate_tasks_no_timetta_calls` — `generate_tasks` не вызывает `adapter.create_task`/`update_task` (мок claude), возвращает нормализованные dict'ы с `project_id`/`task_type`
  - `test_create_tasks_creates_and_returns_urls` — `create_tasks` вызывает `create_task` для каждого dict, собирает результаты с `url`
  - `test_submit_requirements_wrapper` — обёртка == generate+create (существующее поведение/результат не изменились)
  - Файл: `tests/test_submit_task.py`

- [x] 7. **Тесты флоу хендлеров** — `tests/test_telegram_handlers.py`
  - `test_handle_text_shows_preview_no_create` — текст → `_run_generate` вызван, `_run_create`/Timetta НЕ вызваны, `pending_submit` сохранён, в ответе клавиатура с `submit_ok`/`submit_cancel`
  - `test_submit_ok_creates_tasks` — callback `submit_ok` → `_run_create` вызван, `pending_submit` очищен, ответ с результатами
  - `test_submit_cancel_clears_pending` — callback `submit_cancel` → `pending_submit` удалён
  - `test_text_while_pending_is_correction` — при наличии `pending_submit` текст → перегенерация (`_run_generate` вызван повторно), создание не запускается
  - `test_preview_format_detailed` — `_format_preview` показывает summary/описание/исполнителя/теги
  - Хелпер `make_callback_update` уже есть
  - Файл: `tests/test_telegram_handlers.py`

> **💾 Commit 3** (после задачи 7): `test(telegram): cover task review and correction flow`

---

### Фаза 4 — Документация

- [x] 8. **Docs checkpoint** — `/aif-docs`
  - Обновить `docs/telegram-bot.md`: описать новый флоу (превью → подтверждение → правки), кнопки, поведение «текст = правка пока ждём подтверждения»
  - Проверить README — при необходимости обновить раздел Telegram Bot
  - Файлы: `docs/telegram-bot.md`, `README.md`

> **💾 Commit 4** (после задачи 8): `docs(telegram): document task review flow`

---

## Commit Plan

| После задачи | Коммит |
|---|---|
| 1 | `refactor(submit): split generate_tasks and create_tasks` |
| 5 | `feat(telegram): review tasks before uploading to Timetta` |
| 7 | `test(telegram): cover task review and correction flow` |
| 8 | `docs(telegram): document task review flow` |

## Примечания по реализации

### Совместимость CLI
`task-submit` и `enrich` не должны измениться: `submit_requirements` остаётся тонкой
обёрткой с прежней сигнатурой и результатом. Тесты на обёртку фиксируют это.

### VPS-sync
Синхронизация кодовой базы (если `vps_remote` задан) выполняется ДО `generate_tasks`
(стек-анализ использует `project_path`). На шаге подтверждения повторная синхронизация
не нужна.

### Файлы при фото+подпись
`file_id` в Telegram живёт достаточно долго — повторно скачиваем файл на шаге
подтверждения (в `handle_submit_ok`), не храним байты в `chat_data`. Прикрепление —
после успешного создания задач.

### Состояние «ждём подтверждения»
Лёгкое состояние через флаг `chat_data["pending_submit"]` — БЕЗ `ConversationHandler`
(консистентно с текущей inline/callback-навигацией; см. задачи 15/16 в
`telegram-bot-interface.md`, помеченные SUPERSEDED). In-memory, сбрасывается при
рестарте бота — это приемлемо.

### Неоднозначность «правка vs новое требование»
Пока есть `pending_submit`, любой текст трактуется как правка к текущему набору
(выбор пользователя). Чтобы начать заново — `❌ Отмена`, затем новый текст.
