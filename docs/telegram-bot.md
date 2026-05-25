[Back to README](../README.md) · [Submit Pipeline →](submit-pipeline.md)

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
  ├── /start                    → инструкция по использованию
  ├── /project                  → текущий проект чата
  ├── /tasks                    → последние созданные задачи
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
| `/start` | Приветствие и краткая инструкция |
| `/project` | Показать project_id и sprint_id текущего чата |
| `/tasks` | Список URL последних созданных задач (текущая сессия) |

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

Состояние между сообщениями хранится в `context.user_data` (in-memory per-session). При рестарте бота — сбрасывается.

| Ключ | Значение |
|---|---|
| `last_task_ids` | `list[str]` — ID последних созданных задач |

Для прикрепления фото/файла без подписи — предварительно создайте задачу отправив текст.

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
