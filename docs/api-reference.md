[← Начало работы](getting-started.md) · [Back to README](../README.md)

# API-справочник

## Task — модель задачи

```python
from tracker_assistant import Task

task = Task(
    project_id="uuid",         # ID проекта в Timetta (обязательно)
    summary="Название",        # название (обязательно)
    description="Описание",    # markdown-описание
    task_type="",              # тип задачи (опционально)
    tags=["backend"],          # теги
    assignee="user-uuid",      # ID/логин исполнителя
    comments=["Комментарий"],  # комментарии — добавляются после создания
    attachments=["./spec.pdf"],# пути к файлам — прикрепляются после создания
    extra={"priority": 2},     # любые дополнительные поля API
)
```

### Поля Task

| Поле | Тип | Обязательно | Описание |
|---|---|---|---|
| `project_id` | `str` | да | ID проекта в Timetta |
| `summary` | `str` | да | Название задачи |
| `description` | `str` | нет | Описание в markdown |
| `task_type` | `str` | нет | Тип задачи (typeId в API) |
| `tags` | `list[str]` | нет | Теги |
| `assignee` | `str` | нет | ID/логин исполнителя |
| `comments` | `list[str]` | нет | Тексты комментариев |
| `attachments` | `list[str]` | нет | Пути к файлам |
| `extra` | `dict` | нет | Доп. поля Timetta API |

### Методы Task

```python
# Создать из словаря (например, из JSON-файла)
task = Task.from_dict({"project_id": "uuid", "summary": "S", "tags": ["x"]})

# Сформировать тело запроса к API
body = task.to_api_body()
# → {"projectId": "uuid", "name": "S", "tags": ["x"]}
```

---

## Формат task.json

Минимальный пример:

```json
{
  "project_id": "your-project-uuid",
  "summary": "Название задачи"
}
```

Полный пример со всеми полями:

```json
{
  "project_id": "your-project-uuid",
  "summary": "Добавить API для подтверждения заказа",
  "description": "## Контекст\n\nПокупатель подтверждает заказ через мобильное приложение.\n\n## Критерии приёмки\n\n- POST /orders/{id}/confirm возвращает 200\n- Статус заказа меняется на confirmed",
  "tags": ["backend", "api"],
  "assignee": "user-uuid",
  "comments": [
    "Обсудить на стендапе во вторник"
  ],
  "attachments": [
    "./docs/api-spec.pdf"
  ],
  "extra": {
    "priority": 2
  }
}
```

---

## TimettaAdapter

```python
from tracker_assistant import TimettaAdapter

adapter = TimettaAdapter(token="your_bearer_token")
```

### Методы адаптера

| Метод | Описание |
|---|---|
| `get_projects()` | Список всех проектов |
| `create_task(task)` | Создать задачу |
| `get_task(task_id)` | Получить задачу по ID |
| `update_task(task_id, **fields)` | Обновить поля задачи |
| `add_comment(task_id, text)` | Добавить комментарий (None при 404) |
| `attach_file(task_id, filepath)` | Прикрепить файл (None при 404) |

#### get_projects()

```python
projects = adapter.get_projects()
# → [{"id": "uuid-1", "name": "Мой проект", "code": "MYPROJ"}, ...]
```

#### create_task(task)

```python
result = adapter.create_task(task)
print(result["id"])  # "task-uuid-42"
```

#### add_comment(task_id, text)

```python
adapter.add_comment("task-uuid-42", "Готово к ревью")
# Возвращает None если endpoint не поддерживается (404)
```

#### attach_file(task_id, filepath)

```python
adapter.attach_file("task-uuid-42", "/path/to/spec.pdf")
# Возвращает None если endpoint не поддерживается (404)
```

#### update_task(task_id, **fields)

```python
adapter.update_task("task-uuid-42", name="Новое название", priority=3)
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

1. Вызывает `adapter.create_task(task)` — создаёт задачу
2. Для каждого `task.comments` вызывает `adapter.add_comment()`
3. Для каждого `task.attachments` вызывает `adapter.attach_file()`

`root` используется для разрешения относительных путей к вложениям.

---

## Обработка ошибок

При HTTP-ошибке адаптер бросает `RuntimeError` с кодом и телом ответа:

```python
try:
    result = adapter.create_task(task)
except RuntimeError as e:
    print(e)  # "Timetta POST /ProjectTasks → 422: {...}"
```

Методы `add_comment` и `attach_file` при 404 возвращают `None` (graceful degradation).

---

## Логирование

Все компоненты используют стандартный `logging`. Имена логгеров:

| Логгер | Модуль |
|---|---|
| `tracker_assistant.adapters.timetta_adapter` | HTTP-запросы |
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
