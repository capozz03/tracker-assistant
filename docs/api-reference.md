[← Submit Pipeline](submit-pipeline.md) · [Back to README](../README.md) · [Timetta API: нюансы →](timetta-quirks.md)

# API-справочник

## Task — модель задачи

```python
from tracker_assistant import Task

task = Task(
    project_id="uuid",           # ID проекта в Timetta (обязательно)
    summary="Название",          # название (обязательно)
    description="Описание",      # markdown-описание
    task_type="968f71c6-...",     # typeId в API (обязателен для создания)
    assignee="user-uuid",        # ID исполнителя
    tags=["tag-uuid"],           # теги — конвертируются в DirectorySetEntry при PATCH
    comments=["Комментарий"],    # добавляются после создания
    attachments=["./spec.pdf"],  # прикрепляются после создания
    extra={"sprintId": "uuid"},  # любые дополнительные поля API
)
```

### Поля Task

| Поле | Тип | Обязательно | Описание |
|---|---|---|---|
| `project_id` | `str` | да | ID проекта в Timetta |
| `summary` | `str` | да | Название задачи |
| `description` | `str` | нет | Описание в markdown |
| `task_type` | `str` | **да для создания** | typeId в API. Дефолт: `968f71c6-6b38-4845-963a-b2d07ec95185` |
| `assignee` | `str` | нет | UUID исполнителя |
| `tags` | `list[str]` | нет | UUID тегов — автоматически конвертируются при PATCH |
| `comments` | `list[str]` | нет | Тексты комментариев |
| `attachments` | `list[str]` | нет | Пути к файлам |
| `extra` | `dict` | нет | Доп. поля: `sprintId`, `storyPoints` и др. |

### Методы Task

```python
# Создать из словаря (из JSON-файла)
task = Task.from_dict({"project_id": "uuid", "summary": "S", "task_type": "tId"})

# Сформировать тело запроса к API
body = task.to_api_body()
# → {"projectId": "uuid", "name": "S", "typeId": "tId"}
```

---

## Формат task.json

Шаблон с обязательными полями:

```json
{
  "project_id": "your-project-uuid",
  "task_type": "968f71c6-6b38-4845-963a-b2d07ec95185",
  "summary": "Название задачи"
}
```

Полный пример:

```json
{
  "project_id": "your-project-uuid",
  "task_type": "968f71c6-6b38-4845-963a-b2d07ec95185",
  "summary": "Backend: API полнотекстового поиска",
  "description": "## Контекст\n\nРеализовать поиск по заголовку и описанию туров.\n\n## Критерии приёмки\n\n- GET /tours?q=камчатка возвращает релевантные результаты\n- Поиск регистронезависимый",
  "assignee": "user-uuid",
  "comments": ["Обсудить на стендапе во вторник"],
  "attachments": ["./docs/api-spec.pdf"],
  "extra": {
    "sprintId": "941a82f6-7f26-4ecb-af63-2f2f5ba02b91",
    "storyPoints": 5
  }
}
```

---

## TimettaAdapter

```python
from tracker_assistant import TimettaAdapter

adapter = TimettaAdapter(token="your_bearer_token")
# Опционально: переопределить директорию тегов
adapter = TimettaAdapter(token="tok", tags_dir_id="custom-dir-uuid")
```

### Методы адаптера

| Метод | Описание |
|---|---|
| `get_projects()` | Список всех проектов |
| `get_users()` | Список пользователей Timetta |
| `get_tags()` | Список тегов (из DirectoryEntries) |
| `create_task(task)` | Создать задачу (без тегов в теле) |
| `get_task(task_id)` | Получить задачу по UUID |
| `update_task(task_id, **fields)` | Обновить поля; теги → DirectorySetEntry |
| `add_comment(task_id, text)` | Добавить комментарий (None при 404) |
| `attach_file(task_id, filepath)` | Прикрепить файл (None при 404) |

#### get_tags()

```python
tags = adapter.get_tags()
# → [{"id": "c98cabfb-...", "name": "Фронтенд"}, {"id": "e9967692-...", "name": "Бекенд"}, ...]
```

Теги хранятся в `/DirectoryEntries` с фильтром по `directoryId`.

#### create_task(task)

```python
result = adapter.create_task(task)  # tags в теле НЕ передаются — установи через update_task
print(result["id"])  # "task-uuid"
```

#### update_task(task_id, **fields)

```python
# Назначить исполнителя
adapter.update_task("task-uuid", assigneeId="user-uuid")

# Установить теги — строки UUID принимаются, конвертируются в DirectorySetEntry автоматически
adapter.update_task("task-uuid", tags=["c98cabfb-...", "e9967692-..."])

# Поставить спринт
adapter.update_task("task-uuid", sprintId="941a82f6-...")
```

> **Важно:** теги передаются как `Collection(WP.DirectorySetEntry)`. Метод `_format_tags()` конвертирует строки-UUID автоматически. Подробнее — [Timetta API: нюансы](timetta-quirks.md#2-теги--collectionwpdirectorysetentry).

#### _format_tags(tags)

Внутренний метод конвертации:

```python
# Принимает строки или {id: "uuid"}
adapter._format_tags(["c98cabfb-...", {"id": "e9967692-..."}])
# → [
#     {"directoryEntryId": "c98cabfb-...", "directoryId": "d7f2a0a2-..."},
#     {"directoryEntryId": "e9967692-...", "directoryId": "d7f2a0a2-..."},
#   ]
```

#### add_comment(task_id, text)

```python
adapter.add_comment("task-uuid", "Готово к ревью")
# Возвращает None если endpoint не поддерживается (404)
```

#### attach_file(task_id, filepath)

```python
adapter.attach_file("task-uuid", "/path/to/spec.pdf")
# Возвращает None если endpoint не поддерживается (404)
```

---

## Pipeline-функции

### create_task(adapter, task, *, root=None)

```python
from tracker_assistant import create_task
from pathlib import Path

result = create_task(adapter, task, root=Path("."))
```

1. `adapter.create_task(task)` — создаёт задачу (без тегов)
2. Для каждого `task.comments` — `adapter.add_comment()`
3. Для каждого `task.attachments` — `adapter.attach_file()`

`root` — для разрешения относительных путей к вложениям.

---

## CLI-команды

### task_cli.py

| Команда | Описание |
|---|---|
| `list-projects` | Список проектов |
| `list-users [--no-cache]` | Список пользователей (кеш 24 ч) |
| `list-tags [--no-cache]` | Список тегов (кеш 24 ч) |
| `create --input task.json` | Создать задачу из JSON |
| `update --issue ID [--assignee UUID] [--set-tags UUIDs] [--add-tag UUID]` | Обновить задачу |
| `add-comment --issue ID --text "..."` | Добавить комментарий |
| `attach-file --issue ID --file path` | Прикрепить файл |

```bash
uv run python scripts/task_cli.py --log-level DEBUG list-projects
uv run python scripts/task_cli.py update --issue task-uuid --set-tags "uuid1,uuid2"
```

### enrich_task.py

Обогащает сырой JSON задачи через `claude -p`: подбирает теги, исполнителя, формирует описание.

```bash
uv run python scripts/enrich_task.py --input raw.json --output task.json
echo '{"project_id":"uuid","summary":"черновик"}' | uv run python scripts/enrich_task.py
```

| Аргумент | Описание |
|---|---|
| `--input` | Путь к JSON-файлу (по умолчанию stdin) |
| `--output` | Путь для записи (по умолчанию stdout) |
| `--root` | Корень сервиса (для `.env` и кеша) |
| `--no-cache` | Игнорировать кеш |

### submit_task.py

Полный конвейер: требования → стек → Claude → задачи в Timetta. [Подробная документация →](submit-pipeline.md)

```bash
uv run python scripts/submit_task.py \
  --requirements-file tasks.md \
  --project-id <uuid> \
  --sprint-id <sprint-uuid> \
  --project-path /path/to/codebase
```

---

## Обработка ошибок

```python
try:
    result = adapter.create_task(task)
except RuntimeError as e:
    print(e)  # "Timetta POST /Issues → 400: {entity cannot be null}"
```

`add_comment` и `attach_file` при 404 возвращают `None` (graceful degradation).

---

## Кеширование

`get_users()` и `get_tags()` кешируются в `cache/users.json` / `cache/tags.json` (TTL 24 ч).

```python
from tracker_assistant.io_utils import load_cached

# Использовать кеш (или запросить если устарел)
tags = load_cached(root, "tags", adapter.get_tags)

# Принудительно обновить
tags = load_cached(root, "tags", adapter.get_tags, no_cache=True)
```

---

## Логирование

| Логгер | Модуль |
|---|---|
| `tracker_assistant.adapters.timetta_adapter` | HTTP-запросы |
| `tracker_assistant.pipeline` | Создание задач |

```bash
uv run python scripts/task_cli.py --log-level DEBUG list-projects
```

## See Also

- [Submit Pipeline](submit-pipeline.md) — авто-создание задач из требований
- [Timetta API: нюансы](timetta-quirks.md) — форматы, ошибки, подводные камни
- [OpenAPI Spec](timetta-openapi.yaml) — полная спецификация эндпоинтов
