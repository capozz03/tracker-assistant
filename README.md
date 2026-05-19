# Tracker Assistant

> Минималистичный Python-клиент для Timetta: получить проекты, создать задачу.

Тонкая обёртка над Timetta OData v4 API. Без черновиков, без шаблонов, без промежуточных шагов — задача создаётся напрямую.

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
```

## Возможности

- **Список проектов** — получить все проекты из Timetta API
- **Создание задачи** — с названием, описанием, тегами, исполнителем
- **Комментарии** — добавить комментарии сразу после создания задачи
- **Вложения** — прикрепить файлы к задаче
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

| Команда | Описание |
|---|---|
| `list-projects` | Список проектов |
| `create --input task.json` | Создать задачу из JSON-файла |
| `add-comment --issue ID --text "..."` | Добавить комментарий к задаче |
| `attach-file --issue ID --file path` | Прикрепить файл к задаче |

```bash
uv run python scripts/task_cli.py --log-level DEBUG list-projects
uv run python scripts/task_cli.py create --input task.json --root .
uv run python scripts/task_cli.py add-comment --issue task-uuid --text "готово"
uv run python scripts/task_cli.py attach-file --issue task-uuid --file ./spec.pdf
```

## Использование как библиотека

```python
from tracker_assistant import Task, TimettaAdapter, list_projects, create_task

adapter = TimettaAdapter(token="your_bearer_token")

# Список проектов
projects = list_projects(adapter)

# Создание задачи
task = Task(
    project_id="your-project-uuid",
    summary="Новая задача",
    tags=["backend"],
    assignee="user-uuid",
    comments=["Первый комментарий"],
)
result = create_task(adapter, task)
print(result["id"])  # "task-uuid-42"
```

---

## Документация

| Раздел | Описание |
|---|---|
| [Начало работы](docs/getting-started.md) | Установка, настройка .env, первый запуск |
| [API-справочник](docs/api-reference.md) | Task, адаптер, формат task.json |

## Изоляция в workspace

Этот сервис изолирован через [ai-factory](https://github.com/capozz03/ai-assistant) стандарт:

- **`CLAUDE.md`** — контекстная изоляция: агент знает только об этом сервисе
- **`.mcp.json`** — только filesystem MCP-сервер, ограниченный директорией сервиса
- **`cwd` в topic_config.json** — процесс агента стартует только в `tracker-assistant/`

## Требования

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (менеджер пакетов)
- Bearer-токен Timetta (OAuth 2.0)
