[← Submit Pipeline](submit-pipeline.md) · [Back to README](../README.md) · [API-справочник →](api-reference.md)

# Telegram Bot

Telegram-бот для управления задачами Timetta: создание из текста/фото, прикрепление файлов, мульти-проектность, синхронизация кодовой базы с VPS.

## Быстрый старт

### 1. Получите токен бота

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте `/newbot`, следуйте инструкциям
3. Скопируйте токен вида `123456:ABC-DEF...`

### 2. Настройте .env

```env
TIMETTA_TOKEN=your_timetta_bearer_token
TIMETTA_PROJECT_ID=your_default_project_uuid
TELEGRAM_TOKEN=123456:ABC-DEF...
```

### 3. Запустите бота

```bash
uv run task-telegram
```

Для отладки:

```bash
uv run task-telegram --log-level DEBUG
```

Для проверки конфигурации без запуска:

```bash
uv run task-telegram --dry-run
```

---

## Конфигурация проектов (`telegram_projects.json`)

По умолчанию бот использует `TIMETTA_PROJECT_ID` из `.env`. Для мульти-проектности создайте `telegram_projects.json` в корне:

```json
{
  "default": {
    "project_id": "timetta-project-uuid",
    "sprint_id": "",
    "project_path": null,
    "vps_remote": null
  },
  "chat_123456789": {
    "project_id": "another-uuid",
    "sprint_id": "sprint-uuid",
    "project_path": null,
    "vps_remote": "user@vps.example.com:/srv/myproject"
  }
}
```

| Поле | Тип | Описание |
|---|---|---|
| `project_id` | string | UUID проекта в Timetta |
| `sprint_id` | string | UUID спринта (опционально) |
| `project_path` | string\|null | Путь к кодовой базе для анализа стека |
| `vps_remote` | string\|null | SSH-путь или git URL для синхронизации кодовой базы |

Ключ `"chat_<chat_id>"` (например, `"chat_123456789"`) привязывает конфигурацию к конкретному чату. Ключ `"default"` — fallback для всех остальных.

---

## Флоу обработки сообщений

```
Входящее сообщение
  ├── /start                    → приветствие + inline-кнопки (Выбрать проект / Избранные)
  ├── /project                  → список проектов Timetta API как inline-клавиатура
  ├── /projects                 → листаемый список из telegram_projects.json (5 на страницу)
  ├── /favorites                → избранные проекты с кнопками выбора и удаления
  ├── /tasks                    → история задач сессии с пагинацией и просмотром деталей
  ├── Нажатие inline-кнопки    → CallbackQueryHandler (выбор проекта / пагинация / история)
  ├── Текст (обычный)           → submit_requirements → ответ с URL задач
  ├── Пересланное сообщение     → извлечение текста → submit_requirements
  ├── Фото + подпись            → submit_requirements(подпись) → attach_file(фото)
  ├── Фото без подписи          → attach_file к последним задачам сессии
  ├── Файл + подпись            → submit_requirements(подпись) → attach_file(файл)
  └── Файл без подписи          → attach_file к последним задачам сессии
```

---

## Команды

| Команда | Описание |
|---|---|
| `/start` | Приветствие, краткая инструкция, inline-кнопки для быстрого старта |
| `/project` | Получить список проектов из Timetta API и выбрать активный через кнопки |
| `/projects` | Постраничный список проектов из `telegram_projects.json` (5 на страницу) |
| `/favorites` | Показать избранные проекты; быстрый выбор или удаление из списка |
| `/tasks` | История задач текущей сессии с пагинацией и просмотром деталей |

### Выбор проекта через /project

1. Команда запрашивает проекты через Timetta API и показывает их как inline-клавиатуру
2. Нажатие на кнопку устанавливает проект активным для данного чата
3. Активный проект отмечается `✅` в списке
4. После выбора появляется кнопка «⭐ Добавить в избранные»

### Выбор проекта через /projects (пагинация)

`/projects` листает проекты из `telegram_projects.json` постранично — удобно, если проектов много:

1. Команда показывает первую страницу (до 5 проектов)
2. Кнопки `← Назад` / `Далее →` для навигации между страницами
3. Нажатие на проект устанавливает его активным

### Избранные проекты

- Избранные хранятся в `context.user_data["favorites"]` (per-user, сбрасывается при рестарте)
- `/favorites` отображает список с кнопками `⭐ Выбрать` и `✖ Убрать`
- Можно добавить проект в избранные сразу после выбора через `/project`

### История задач через /tasks

`/tasks` показывает все задачи, созданные за текущую сессию:

1. Команда выводит постраничный список задач (5 на страницу)
2. Нажатие на задачу показывает её детали: название и URL в Timetta
3. История сбрасывается при рестарте бота

---

## VPS-синхронизация кодовой базы

Если задан `vps_remote`, бот синхронизирует кодовую базу перед анализом стека.

### Поддерживаемые форматы

| Формат | Стратегия |
|---|---|
| `user@host:/srv/app` | rsync по SSH |
| `host:/srv/app` | rsync по SSH |
| `https://github.com/org/repo` | git clone / pull |
| `git@github.com:org/repo.git` | git clone / pull |
| `/absolute/local/path` | локальная директория (без синхронизации) |

### Как это работает

1. Бот отправляет: `🔄 Синхронизирую кодовую базу…`
2. Запускает `rsync -avz --delete` или `git pull --ff-only` в фоне (`asyncio.to_thread`)
3. Кеш хранится в `cache/vps/<slug>/`
4. После синхронизации — обычный анализ стека через `submit_requirements`

### Требования

- **rsync**: должен быть установлен на сервере и иметь SSH-доступ к VPS
- **git**: для git-стратегии

### Проверка доступа к VPS

```bash
# Проверить rsync вручную
rsync -avz --delete user@vps.example.com:/srv/myproject/ /tmp/test-sync/

# Проверить git
git clone --depth=1 https://github.com/org/repo /tmp/test-clone
```

---

## CLI-параметры

```bash
uv run task-telegram [OPTIONS]

Options:
  --root ROOT           Корень проекта (default: текущая директория)
  --log-level LEVEL     DEBUG | INFO | WARNING | ERROR | CRITICAL (default: INFO)
  --dry-run             Валидировать конфиг без запуска бота
```

### Примеры

```bash
# Запустить из другой директории
uv run task-telegram --root /srv/tracker-assistant

# Отладочное логирование всех HTTP-запросов
uv run task-telegram --log-level DEBUG

# Проверить конфиг без запуска
uv run task-telegram --dry-run
✅ Конфиг валиден: 2 проект(ов) загружено.
  default: project_id='timetta-project-uuid'
  chat_123456789: project_id='another-uuid'
```

---

## Структура модуля

```
src/tracker_assistant/telegram/
  __init__.py     # Публичный API: run_bot(config)
  config.py       # BotConfig, ProjectConfig, load_config(root)
  bot.py          # Application factory, регистрация хендлеров
  handlers.py     # handle_text, handle_photo, handle_document, команды
  pagination.py   # Утилита пагинации: paginate, make_nav_keyboard, make_select_keyboard
  projects.py     # ProjectRegistry — маппинг chat_id → ProjectConfig
  vps_sync.py     # rsync / git clone синхронизация кодовой базы
  cli.py          # Тонкий CLI entry point
```

**Зависимости модуля:**
- `handlers.py` → `tracker_assistant.submit` (submit_requirements)
- `handlers.py` → `tracker_assistant.timetta` (attach_file)
- `bot.py` → `handlers.py`, `config.py`, `projects.py`
- `vps_sync.py` → только stdlib (subprocess, pathlib)
- `cli.py` → `__init__.py` (run_bot)

---

## Хранение состояния

Состояние хранится in-memory и сбрасывается при рестарте бота.

| Хранилище | Ключ | Значение |
|---|---|---|
| `user_data` | `last_task_ids` | `list[str]` — ID последних созданных задач |
| `user_data` | `task_history` | `list[{"id": str, "summary": str, "url": str}]` — история задач сессии |
| `user_data` | `favorites` | `list[{"id": str, "name": str}]` — избранные проекты |
| `user_data` | `proj_page` | `int` — текущая страница в `/projects` |
| `user_data` | `task_page` | `int` — текущая страница в `/tasks` |
| `chat_data` | `active_project_id` | `str` — UUID выбранного проекта (per-chat) |
| `chat_data` | `_project_cache` | `dict[str, str]` — кеш `{uuid: name}` из последнего вызова API |

Для прикрепления фото/файла без подписи — предварительно создайте задачу, отправив текст.

---

## Диагностика

### Бот не отвечает

1. Проверьте `TELEGRAM_TOKEN` в `.env`
2. Запустите `uv run task-telegram --dry-run`
3. Проверьте логи с `--log-level DEBUG`

### Задачи не создаются

1. Проверьте `TIMETTA_TOKEN` и `TIMETTA_PROJECT_ID`
2. Проверьте `project_id` в `telegram_projects.json`
3. Убедитесь, что project_id существует: `uv run task-cli list-projects`

### Синхронизация VPS не работает

1. Проверьте SSH-доступ вручную
2. Убедитесь, что `rsync` установлен: `rsync --version`
3. Смотрите логи с `--log-level DEBUG` — каждый вызов subprocess логируется
