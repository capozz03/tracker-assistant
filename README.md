# Tracker Assistant

> Python-клиент для Timetta: управление задачами и автоматическое создание из требований.

Тонкая обёртка над Timetta OData v4 API. Создаёт задачи вручную через CLI или автоматически — из текста требований через `submit_task.py`.

## Быстрый старт

```bash
# Установить зависимости
uv sync

# Создать .env с токеном
echo "TIMETTA_TOKEN=your_bearer_token" >> .env

# Список проектов
uv run python scripts/task_cli.py list-projects

# Создать задачу из JSON-файла
uv run python scripts/task_cli.py create --input task.json

# Автоматически создать задачи из файла требований
uv run python scripts/submit_task.py \
  --requirements-file tasks.md \
  --project-id <uuid> \
  --sprint-id <uuid>
```

## Возможности

- **Submit pipeline** — текст требований → анализ стека → разбивка на задачи → создание в Timetta
- **Telegram Bot** — создание задач через бот: текст, фото, документы, пересланные сообщения
- **Создание задачи** — с названием, описанием, тегами, исполнителем, спринтом
- **Обогащение задачи** — `enrich-task` форматирует сырое описание через `claude -p`
- **Комментарии и вложения** — добавить к задаче сразу после создания
- **Список пользователей и тегов** — `list-users`, `list-tags` с кешированием на 24 ч
- **VPS-синхронизация** — бот синхронизирует кодовую базу через rsync/git перед анализом
- **Verbose-логирование** — все HTTP-запросы в DEBUG-режиме

## Пример: task.json

```json
{
  "project_id": "your-project-uuid",
  "summary": "Добавить API для подтверждения заказа",
  "description": "## Контекст\n\nПокупатель подтверждает заказ через мобильное приложение.",
  "tags": ["backend", "api"],
  "assignee": "user-uuid",
  "comments": ["Обсудить с командой на следующем стендапе"]
}
```

## CLI-команды

| Команда | Точка входа | Описание |
|---|---|---|
| `uv run task-cli` | `task_cli.py` | Управление задачами через CLI |
| `uv run task-submit` | `submit.cli` | Создание задач из требований |
| `uv run task-enrich` | `enrich.cli` | Обогащение задачи через LLM |
| `uv run task-telegram` | `telegram.cli` | Запуск Telegram-бота |

### task-cli — команды

| Команда | Описание |
|---|---|
| `list-projects` | Список проектов |
| `list-users` | Список пользователей (кеш 24 ч) |
| `list-tags` | Список тегов (кеш 24 ч) |
| `create --input task.json` | Создать задачу из JSON-файла |
| `update --issue ID --field value` | Обновить поля задачи |
| `add-comment --issue ID --text "..."` | Добавить комментарий |
| `attach-file --issue ID --file path` | Прикрепить файл |

### task-telegram — Telegram Bot

```bash
# Запустить бота (TELEGRAM_TOKEN должен быть в .env)
uv run task-telegram

# Проверить конфиг без запуска
uv run task-telegram --dry-run

# Отладочное логирование
uv run task-telegram --log-level DEBUG
```

> Бот сначала показывает сгенерированные задачи на проверку (превью с кнопками
> «Создать» / «Отмена»); правки можно прислать текстом. Выгрузка в Timetta — только
> после подтверждения. Подробнее: [docs/telegram-bot.md](docs/telegram-bot.md).

```bash
uv run python scripts/task_cli.py list-users
uv run python scripts/task_cli.py list-tags
uv run python scripts/task_cli.py create --input task.json --root .
uv run python scripts/task_cli.py add-comment --issue task-uuid --text "готово"
```

## submit_task.py — конвейер из требований

```bash
# Из файла требований с привязкой к спринту
uv run python scripts/submit_task.py \
  --requirements-file tasks.md \
  --project-id <uuid> \
  --sprint-id <uuid>

# Из текста с анализом кодовой базы
uv run python scripts/submit_task.py \
  --requirements "Добавить мультиселект регионов в фильтры" \
  --project-id <uuid> \
  --project-path /path/to/your/project
```

Конвейер: анализ стека (`has_frontend`, `has_backend`) → `claude -p` делит задачу по слоям → создаёт задачи с тегами и исполнителем.

## Использование как библиотека

```python
from tracker_assistant import Task, TimettaAdapter, list_projects, create_task

adapter = TimettaAdapter(token="your_bearer_token")
projects = list_projects(adapter)

task = Task(
    project_id="your-project-uuid",
    summary="Новая задача",
    tags=["backend"],
    assignee="user-uuid",
)
result = create_task(adapter, task)
print(result["id"])
```

---

## Документация

| Раздел | Описание |
|---|---|
| [Начало работы](docs/getting-started.md) | Установка, .env, первый запуск |
| [Submit Pipeline](docs/submit-pipeline.md) | Автосоздание задач из требований |
| [Telegram Bot](docs/telegram-bot.md) | Установка, конфигурация, команды бота |
| [API-справочник](docs/api-reference.md) | Task, TimettaAdapter, CLI-команды |
| [Timetta API: нюансы](docs/timetta-quirks.md) | Подводные камни OData v4 интеграции |
| [OpenAPI Spec](docs/timetta-openapi.yaml) | Swagger-спецификация для новых интеграций |

## Изоляция в workspace

Этот сервис изолирован через [ai-factory](https://github.com/capozz03/ai-assistant) стандарт:

- **`CLAUDE.md`** — контекстная изоляция: агент знает только об этом сервисе
- **`.mcp.json`** — только filesystem MCP-сервер, ограниченный директорией сервиса
- **`cwd` в topic_config.json** — процесс агента стартует только в `tracker-assistant/`

## Требования

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (менеджер пакетов)
- Bearer-токен Timetta (OAuth 2.0)
