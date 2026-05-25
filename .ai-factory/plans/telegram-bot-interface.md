# Telegram Bot Interface

**Ветка:** нет (create_branches: false)  
**Создан:** 2026-05-25  
**Описание:** Слой Telegram-бота для управления задачами Timetta — поддержка текста, пересланных сообщений, вложений (фото), мульти-проектности и синхронизации кодовой базы с VPS.

## Настройки

- **Тестирование:** да
- **Логирование:** verbose (DEBUG)
- **Docs:** да — обязательный checkpoint через `/aif-docs` после завершения

## Архитектура нового модуля

```
src/tracker_assistant/telegram/
  __init__.py        # Публичный API: run_bot(config)
  config.py          # BotConfig, ProjectConfig, load_config(root)
  bot.py             # Application factory, регистрация хендлеров, polling
  handlers.py        # handle_text, handle_photo, handle_document
  projects.py        # ProjectRegistry — маппинг chat_id → ProjectConfig
  vps_sync.py        # Прототип: rsync/git-clone кодовой базы с VPS
  cli.py             # Thin CLI entry point
```

**Правила зависимостей** (следуем ARCHITECTURE.md):
- `telegram/handlers.py` → `tracker_assistant.submit` (публичный API)
- `telegram/handlers.py` → `tracker_assistant.timetta` (attach_file)
- `telegram/bot.py` → `telegram/handlers.py`, `telegram/config.py`
- `telegram/vps_sync.py` → только stdlib (subprocess, pathlib)
- `telegram/cli.py` → `telegram/__init__.py` (тонкая обёртка, ~60 строк)

**Новые env-переменные** (добавить в `.env.example`):
```env
TELEGRAM_TOKEN=your_bot_token_from_botfather
```

**Конфиг проектов** (`telegram_projects.json` в корне):
```json
{
  "default": {
    "project_id": "timetta-project-uuid",
    "sprint_id": "",
    "project_path": null,
    "vps_remote": null
  },
  "chat_123456789": {
    "project_id": "uuid",
    "sprint_id": "sprint-uuid",
    "project_path": null,
    "vps_remote": "user@vps.example.com:/srv/myproject"
  }
}
```

## Флоу хендлеров

```
Входящее сообщение
  ├── Текст (обычный)         → submit_requirements(text) → ответ с URL задач
  ├── Пересланное сообщение   → extract_text(forward) → submit_requirements → ответ
  ├── Фото + подпись          → submit_requirements(caption) → attach_file(photo)
  └── Фото без подписи        → attach_file к последней задаче (из user_data)
```

## Задачи

### Фаза 1 — Фундамент

<!-- parallel: tasks 1, 2, 3 -->
- [x] 1. **Зависимости** — добавить `python-telegram-bot[job-queue]>=20.0` в `pyproject.toml`; `uv sync` для проверки установки
  - Файл: `pyproject.toml`
  - Лог: `logger.info("telegram: python-telegram-bot версия %s", telegram.__version__)`

- [x] 2. **`telegram/config.py`** — конфигурация бота и проектов
  - `ProjectConfig` dataclass: `project_id: str`, `sprint_id: str = ""`, `project_path: Path | None = None`, `vps_remote: str | None = None`
  - `BotConfig` dataclass: `token: str`, `root: Path`, `projects: dict[str, ProjectConfig]`
  - `load_config(root: Path) -> BotConfig` — читает `TELEGRAM_TOKEN` из `.env`, загружает `telegram_projects.json` если есть, иначе создаёт конфиг с `default`-проектом из `TIMETTA_PROJECT_ID`
  - Лог: `logger.debug("load_config: root=%s, projects=%d", root, len(config.projects))`
  - Файл: `src/tracker_assistant/telegram/config.py`

- [x] 3. **`telegram/projects.py`** — реестр проектов
  - `ProjectRegistry(projects: dict[str, ProjectConfig])`
  - `get_project(chat_id: str | int) -> ProjectConfig` — ищет по `f"chat_{chat_id}"`, при отсутствии возвращает `"default"`
  - `list_projects() -> list[tuple[str, ProjectConfig]]`
  - Лог: `logger.debug("ProjectRegistry.get_project: chat_id=%s → project_id=%s", chat_id, project.project_id)`
  - Файл: `src/tracker_assistant/telegram/projects.py`

- [x] 4. **`telegram/bot.py`** + **`telegram/__init__.py`**
  - `build_application(config: BotConfig) -> Application` — создаёт `Application`, регистрирует хендлеры из `handlers.py`
  - `run_bot(config: BotConfig) -> None` — вызывает `app.run_polling()`
  - `__init__.py`: `from .bot import run_bot; __all__ = ["run_bot"]`
  - Лог: `logger.info("bot: запускаем polling, проектов=%d", len(config.projects))`
  - Файлы: `src/tracker_assistant/telegram/bot.py`, `src/tracker_assistant/telegram/__init__.py`

> **💾 Commit 1** (после задачи 4): `feat(telegram): foundation — config, project registry, bot factory`

---

### Фаза 2 — Хендлеры

- [ ] 5. **`telegram/handlers.py`** — текстовые сообщения
  - `make_handlers(registry: ProjectRegistry, adapter_factory, cache_loader) -> list[BaseHandler]`
  - `_handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE)` — async handler
  - Извлечение текста: `update.message.text` (обычный) или `update.message.caption` (фото)
  - Для пересланных: `effective_text = _extract_forwarded_text(update.message)` — проверяет `message.forward_date`, `message.forward_from`, `message.forward_from_chat`
  - Вызов: `submit_requirements(text, project_id, adapter, users, tags, project_path, root, sprint_id)`
  - Ответ: форматированное сообщение с `✅ Создано N задач:\n• <summary> — <url>`
  - Лог: `logger.info("[tg] text: chat=%s len=%d", chat_id, len(text))`
  - Файл: `src/tracker_assistant/telegram/handlers.py`

- [ ] 6. **Фото-хендлер** — добавить в `handlers.py`
  - `_handle_photo(update, context)` — async handler для `MessageHandler(filters.PHOTO, ...)`
  - Скачивает наибольшее фото: `await update.message.photo[-1].get_file()` → `await file.download_to_drive(tmp_path)`
  - Если есть `message.caption` → сначала `submit_requirements(caption)`, затем `attach_file(task_id, tmp_path)` для каждой созданной задачи
  - Если нет caption → достаёт `last_task_ids` из `context.user_data` и прикрепляет к ним
  - `context.user_data["last_task_ids"] = [r["id"] for r in results]` сохраняется после любого создания задач
  - Лог: `logger.info("[tg] photo: chat=%s file_size=%d", chat_id, file_size)`
  - Файл: `src/tracker_assistant/telegram/handlers.py` (добавить в тот же файл)

- [ ] 7. **Document-хендлер** + **вспомогательные команды** — добавить в `handlers.py`
  - `_handle_document(update, context)` — аналогично фото, для `filters.Document.ALL`; скачивает файл, прикрепляет к задачам
  - `/start` → приветственное сообщение с инструкцией
  - `/project` → показать текущий проект чата (project_id, sprint_id)
  - `/tasks` → список последних задач из `context.user_data["last_task_ids"]`
  - Лог: `logger.debug("[tg] command: %s chat=%s", command, chat_id)`
  - Файл: `src/tracker_assistant/telegram/handlers.py`

> **💾 Commit 2** (после задачи 7): `feat(telegram): add message handlers (text, forwarded, photo, document)`

---

### Фаза 3 — VPS-синхронизация

- [ ] 8. **`telegram/vps_sync.py`** — прототип синхронизации кодовой базы
  - `SyncStrategy` enum: `LOCAL`, `SSH_RSYNC`, `GIT_CLONE`
  - `detect_strategy(path_spec: str) -> SyncStrategy`:
    - `user@host:/path` или `host:/path` → `SSH_RSYNC`
    - `git+ssh://...`, `https://...`, `.git` суффикс → `GIT_CLONE`
    - Иначе → `LOCAL`
  - `sync_codebase(path_spec: str, cache_dir: Path) -> Path`:
    - Вычисляет slug из `path_spec`, создаёт `cache_dir / slug /`
    - Диспетчеризует к `_sync_rsync` или `_sync_git` или возвращает `Path(path_spec)` для LOCAL
  - `_sync_rsync(remote: str, local: Path) -> Path`:
    - `subprocess.run(["rsync", "-avz", "--delete", remote + "/", str(local)], check=True)`
    - Создаёт lockfile `.sync_in_progress` на время синхронизации
    - Лог: `logger.info("rsync: %s → %s", remote, local)`
  - `_sync_git(repo_url: str, local: Path) -> Path`:
    - Если `local/.git` существует → `git -C local pull --ff-only`
    - Иначе → `git clone --depth=1 repo_url local`
    - Лог: `logger.info("git %s: %s → %s", "pull" if exists else "clone", repo_url, local)`
  - `get_last_sync_time(local: Path) -> datetime | None` — читает `.sync_timestamp`
  - Файл: `src/tracker_assistant/telegram/vps_sync.py`

- [ ] 9. **Интеграция VPS-sync в хендлеры**
  - Добавить в `handlers.py`: перед вызовом `submit_requirements`, если `project.vps_remote` задан:
    ```python
    project_path = await asyncio.to_thread(
        sync_codebase, project.vps_remote, config.root / "cache" / "vps"
    )
    ```
  - `asyncio.to_thread` — чтобы не блокировать event loop при rsync/git
  - Ответ пользователю: `"🔄 Синхронизирую кодовую базу..."` перед длинной операцией
  - Лог: `logger.info("[tg] vps_sync: %s → %s (%.1fs)", remote, local, elapsed)`
  - Файл: `src/tracker_assistant/telegram/handlers.py`

> **💾 Commit 3** (после задачи 9): `feat(telegram): add VPS codebase sync (rsync + git clone)`

---

### Фаза 4 — CLI и конфигурация

- [ ] 10. **`telegram/cli.py`** + entry point
  - `main() -> int` — парсинг аргументов: `--root`, `--log-level`, `--dry-run` (не запускает polling, только валидирует конфиг)
  - `load_config(root) → run_bot(config)`
  - Добавить в `pyproject.toml`: `task-telegram = "tracker_assistant.telegram.cli:main"`
  - Обновить `.env.example`: добавить `TELEGRAM_TOKEN=...`
  - Добавить `telegram_projects.json.example` в корень репозитория
  - Лог: `logger.info("cli: root=%s dry_run=%s", root, dry_run)`
  - Файлы: `src/tracker_assistant/telegram/cli.py`, `pyproject.toml`, `.env.example`, `telegram_projects.json.example`

> **💾 Commit 4** (после задачи 10): `feat(telegram): add CLI entry point and example configs`

---

### Фаза 5 — Тесты

<!-- parallel: tasks 11, 12, 13 -->
- [ ] 11. **Тесты config и projects**
  - `tests/test_telegram_config.py`:
    - `test_load_config_from_env` — TELEGRAM_TOKEN из env, default project из TIMETTA_PROJECT_ID
    - `test_load_config_with_projects_json` — загрузка из `telegram_projects.json`
    - `test_load_config_missing_token` — SystemExit при отсутствии токена
  - `tests/test_telegram_projects.py`:
    - `test_get_project_by_chat_id` — находит `chat_123`
    - `test_get_project_fallback_default` — fallback на `default`
    - `test_list_projects` — возвращает все проекты
  - Файлы: `tests/test_telegram_config.py`, `tests/test_telegram_projects.py`

- [ ] 12. **Тесты хендлеров**
  - `tests/test_telegram_handlers.py`:
    - Мок `Update` и `Context` через `unittest.mock.AsyncMock`
    - `test_handle_text_calls_submit` — текст → вызывает `submit_requirements` с правильными аргументами
    - `test_handle_forwarded_extracts_text` — пересланное сообщение → извлекает текст
    - `test_handle_photo_with_caption_submits_and_attaches` — фото + подпись → создаёт задачу и прикрепляет
    - `test_handle_photo_no_caption_attaches_to_last` — фото без подписи → прикрепляет из `user_data`
    - `test_handle_text_no_project_error` — нет default проекта → graceful error reply
  - Файл: `tests/test_telegram_handlers.py`

- [ ] 13. **Тесты VPS sync**
  - `tests/test_telegram_vps_sync.py`:
    - `test_detect_strategy_ssh_rsync` — `user@host:/path` → `SSH_RSYNC`
    - `test_detect_strategy_git_clone` — `https://github.com/...` → `GIT_CLONE`
    - `test_detect_strategy_local` — `/absolute/path` → `LOCAL`
    - `test_sync_rsync_calls_subprocess` — мок `subprocess.run`, проверяет аргументы rsync
    - `test_sync_git_clone_fresh` — мок `subprocess.run`, нет `.git` → вызывает `git clone`
    - `test_sync_git_pull_existing` — мок `subprocess.run`, `.git` есть → вызывает `git pull`
  - Файл: `tests/test_telegram_vps_sync.py`

> **💾 Commit 5** (после задачи 13): `test(telegram): add tests for config, handlers, vps_sync`

---

### Фаза 6 — Документация

- [ ] 14. **Docs checkpoint** — `/aif-docs`
  - `docs/telegram-bot.md` — установка, конфигурация, запуск, примеры команд бота
  - Обновить `README.md` — добавить `task-telegram` в таблицу CLI-команд, раздел "Telegram Bot"
  - Обновить `docs/getting-started.md` — секция Telegram Bot
  - Обновить Documentation-таблицу в README

> **💾 Commit 6** (после задачи 14): `docs: add telegram-bot guide and update README`

---

## Commit Plan

| После задачи | Коммит |
|---|---|
| 4 | `feat(telegram): foundation — config, project registry, bot factory` |
| 7 | `feat(telegram): add message handlers (text, forwarded, photo, document)` |
| 9 | `feat(telegram): add VPS codebase sync (rsync + git clone)` |
| 10 | `feat(telegram): add CLI entry point and example configs` |
| 13 | `test(telegram): add tests for config, handlers, vps_sync` |
| 14 | `docs: add telegram-bot guide and update README` |

## Примечания по реализации

### python-telegram-bot v20+ (async)
Вся библиотека асинхронная. Хендлеры — `async def`. Для вызова синхронного кода (rsync, submit_requirements) используй `asyncio.to_thread()`.

### Хранение состояния
Между сообщениями состояние хранится в `context.user_data` (in-memory, сбрасывается при рестарте). Для продакшна (VPS) это нормально — бот stateless по задачам.

### Вложения и Timetta
`TimettaAdapter.attach_file(task_id, filepath)` возвращает `None` при 404 (graceful degradation). Файлы скачиваются во временную директорию `tempfile.mkdtemp()` и удаляются после прикрепления.

### Multi-project: дизайн для будущего
`ProjectRegistry` уже поддерживает несколько проектов. Расширение: добавить команду `/setproject <project_id>` которая пишет в `context.user_data["project_override"]`.

### VPS sync: кеширование
Синхронизация кодовой базы — дорогая операция (rsync по SSH). Кеш в `cache/vps/<slug>/`. Ребилд только если последняя синхронизация > 1 часа назад (`get_last_sync_time()`).
