[← Начало работы](getting-started.md) · [Back to README](../README.md)

# API-справочник

## Task — модель задачи

```python
from tracker_assistant import Task

task = Task(
    queue="MYQUEUE",          # очередь (обязательно)
    summary="Название",       # название (обязательно)
    project_id="42",          # ID проекта (опционально)
    description="Описание",   # markdown-описание
    issue_type="task",        # тип задачи (default: "task")
    tags=["backend"],         # теги
    assignee="ivanov",        # логин исполнителя
    followers=["petrov"],     # наблюдатели
    parent="MYQUEUE-1",       # ключ родительской задачи
    comments=["Комментарий"], # комментарии — добавляются после создания
    attachments=["./spec.pdf"], # пути к файлам — прикрепляются после создания
    extra={"priority": "critical"},  # любые дополнительные поля API
)
```

### Поля Task

| Поле | Тип | Обязательно | Описание |
|---|---|---|---|
| `queue` | `str` | да | Очередь (ключ), например `MYPROJECT` |
| `summary` | `str` | да | Название задачи |
| `project_id` | `str` | нет | ID проекта (`"42"`) |
| `description` | `str` | нет | Описание в markdown |
| `issue_type` | `str` | нет | Тип: `task`, `bug`, `feature`, etc. |
| `tags` | `list[str]` | нет | Теги |
| `assignee` | `str` | нет | Логин исполнителя |
| `followers` | `list[str]` | нет | Логины наблюдателей |
| `parent` | `str` | нет | Ключ родительской задачи |
| `comments` | `list[str]` | нет | Тексты комментариев |
| `attachments` | `list[str]` | нет | Пути к файлам |
| `extra` | `dict` | нет | Доп. поля Yandex Tracker API |

### Методы Task

```python
# Создать из словаря (например, из JSON-файла)
task = Task.from_dict({"queue": "Q", "summary": "S", "tags": ["x"]})

# Сформировать тело запроса к API
body = task.to_api_body()
# → {"queue": "Q", "summary": "S", "type": "task", "tags": ["x"]}
```

---

## Формат task.json

Минимальный пример:

```json
{
  "queue": "MYQUEUE",
  "summary": "Название задачи"
}
```

Полный пример со всеми полями:

```json
{
  "queue": "MYQUEUE",
  "summary": "Добавить API для подтверждения заказа",
  "project_id": "42",
  "description": "## Контекст\n\nПокупатель подтверждает заказ через мобильное приложение.\n\n## Критерии приёмки\n\n- POST /orders/{id}/confirm возвращает 200\n- Статус заказа меняется на confirmed",
  "issue_type": "task",
  "tags": ["backend", "api"],
  "assignee": "ivanov",
  "followers": ["petrov", "sidorov"],
  "parent": "",
  "comments": [
    "Обсудить на стендапе во вторник"
  ],
  "attachments": [
    "./docs/api-spec.pdf"
  ],
  "extra": {
    "priority": "critical"
  }
}
```

---

## YandexTrackerAdapter

```python
from tracker_assistant import YandexTrackerAdapter

adapter = YandexTrackerAdapter(
    token="AgAAAABx...",
    org_id="12345678",
    org_type="cloud",   # "cloud" (X-Cloud-Org-ID) или "yandex" (X-Org-ID)
)
```

### Методы адаптера

| Метод | Описание |
|---|---|
| `get_projects()` | Список всех проектов с автопагинацией |
| `create_issue(task)` | Создать задачу в Tracker |
| `add_comment(key, text)` | Добавить комментарий |
| `attach_file(key, filepath)` | Прикрепить файл (multipart) |
| `get_issue(key)` | Получить задачу по ключу |
| `update_issue(key, **fields)` | Обновить поля задачи |

#### get_projects()

```python
projects = adapter.get_projects()
# → [{"id": "1", "name": "Мой проект", "shortName": "MYPROJ", ...}, ...]
```

Автоматически пагинирует (по 50 проектов на страницу).

#### create_issue(task)

```python
result = adapter.create_issue(task)
print(result["key"])  # "MYQUEUE-42"
```

#### add_comment(issue_key, text)

```python
adapter.add_comment("MYQUEUE-42", "Готово к ревью")
```

#### attach_file(issue_key, filepath)

```python
adapter.attach_file("MYQUEUE-42", "/path/to/spec.pdf")
```

#### update_issue(issue_key, **fields)

```python
adapter.update_issue("MYQUEUE-42", summary="Новое название", priority="low")
```

---

## Pipeline-функции

### list_projects(adapter)

```python
from tracker_assistant import list_projects

projects = list_projects(adapter)
```

Обёртка над `adapter.get_projects()` с DEBUG-логированием.

### create_task(adapter, task, *, root=None)

```python
from tracker_assistant import create_task
from pathlib import Path

result = create_task(adapter, task, root=Path("."))
```

1. Вызывает `adapter.create_issue(task)` — создаёт задачу
2. Для каждого `task.comments` вызывает `adapter.add_comment()`
3. Для каждого `task.attachments` вызывает `adapter.attach_file()`

`root` используется для разрешения относительных путей к вложениям.

---

## Обработка ошибок

При HTTP-ошибке адаптер бросает `RuntimeError` с кодом и телом ответа:

```python
try:
    result = adapter.create_issue(task)
except RuntimeError as e:
    print(e)  # "Yandex Tracker POST /issues → 422: {...}"
```

---

## Логирование

Все компоненты используют стандартный `logging`. Имена логгеров:

| Логгер | Модуль |
|---|---|
| `tracker_assistant.adapters.yandex_tracker_adapter` | HTTP-запросы |
| `tracker_assistant.pipeline` | Создание задач |

Настройка уровня:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Или через CLI:

```bash
python scripts/task_cli.py --log-level DEBUG list-projects
```

## See Also

- [Начало работы](getting-started.md) — установка, настройка, первый запуск
- [README](../README.md) — обзор проекта
