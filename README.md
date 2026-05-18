# Tracker Assistant

> Минималистичный Python-клиент для Yandex Tracker: получить проекты, создать задачу.

Тонкая обёртка над Yandex Tracker API. Без черновиков, без шаблонов, без промежуточных шагов — задача создаётся напрямую.

## Быстрый старт

```bash
# Установить зависимости
uv sync

# Создать .env с токенами
echo "YANDEX_TRACKER_TOKEN=your_token" >> .env
echo "YANDEX_TRACKER_ORG_ID=your_org_id" >> .env

# Список проектов
uv run python scripts/task_cli.py list-projects

# Создать задачу из JSON-файла
uv run python scripts/task_cli.py create --input task.json
```

## Возможности

- **Список проектов** — получить все проекты организации из API
- **Создание задачи** — с названием, описанием, тегами, исполнителем, наблюдателями
- **Комментарии** — добавить комментарии сразу после создания задачи
- **Вложения** — прикрепить файлы к задаче
- **Verbose-логирование** — все HTTP-запросы в DEBUG-режиме

## Пример: task.json

```json
{
  "queue": "MYPROJECT",
  "summary": "Добавить API для подтверждения заказа",
  "description": "## Контекст\n\nПокупатель подтверждает заказ через мобильное приложение.",
  "issue_type": "task",
  "tags": ["backend", "api"],
  "assignee": "ivanov",
  "comments": ["Обсудить с командой на следующем стендапе"]
}
```

## CLI-команды

| Команда | Описание |
|---|---|
| `list-projects` | Список проектов организации |
| `create --input task.json` | Создать задачу из JSON-файла |
| `add-comment --issue KEY --text "..."` | Добавить комментарий к задаче |
| `attach-file --issue KEY --file path` | Прикрепить файл к задаче |

```bash
uv run python scripts/task_cli.py --log-level DEBUG list-projects
uv run python scripts/task_cli.py create --input task.json --root .
uv run python scripts/task_cli.py add-comment --issue PROJ-123 --text "готово"
uv run python scripts/task_cli.py attach-file --issue PROJ-123 --file ./spec.pdf
```

## Использование как библиотека

```python
from tracker_assistant import Task, YandexTrackerAdapter, list_projects, create_task

adapter = YandexTrackerAdapter(
    token="...", org_id="...", org_type="cloud"  # или "yandex"
)

# Список проектов
projects = list_projects(adapter)

# Создание задачи
task = Task(
    queue="MYQUEUE",
    summary="Новая задача",
    tags=["backend"],
    assignee="ivanov",
    comments=["Первый комментарий"],
)
result = create_task(adapter, task)
print(result["key"])  # "MYQUEUE-42"
```

---

## Документация

| Раздел | Описание |
|---|---|
| [Начало работы](docs/getting-started.md) | Установка, настройка .env, первый запуск |
| [API-справочник](docs/api-reference.md) | Task, адаптер, формат task.json |

## Требования

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (менеджер пакетов)
- Токен OAuth и Org ID Yandex Tracker
