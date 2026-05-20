---
name: timetta-api
description: >-
  Паттерны и конвенции для работы с Timetta OData v4 API в проекте tracker-assistant.
  Используй при добавлении операций с задачами, расширении адаптера, изменении pipeline или
  CLI-команд. Охватывает: структуру адаптера, модель Task, кеширование, обработку ошибок,
  шаблоны CLI-команд.
argument-hint: "[операция: adapter|pipeline|cli|model|cache]"
---

# Timetta API — паттерны и конвенции

## Архитектура (3 слоя)

```
scripts/task_cli.py        ← CLI: argparse, форматирование вывода
src/tracker_assistant/
  pipeline.py              ← Оркестрация: список проектов, создание задачи
  adapters/
    timetta_adapter.py     ← HTTP-клиент: все запросы к API
  models.py                ← Модель данных: Task dataclass
  io_utils.py              ← Утилиты: .env, JSON, TTL-кеш
```

**Правило:** CLI → pipeline → adapter. Никаких прямых HTTP-вызовов из CLI или pipeline.

## Адаптер (TimettaAdapter)

Базовый URL: `https://api.timetta.com/odata`  
Аутентификация: `Authorization: Bearer <token>` (из `.env`: `TIMETTA_TOKEN`)

```python
# Паттерн метода адаптера
def get_something(self) -> list[dict[str, Any]]:
    url = f"{self.base_url}/Something"
    response = self._request("GET", url)
    return response.get("value", [])

def create_something(self, payload: dict) -> dict[str, Any]:
    url = f"{self.base_url}/Something"
    return self._request("POST", url, json=payload)
```

Для файлов (multipart upload):
```python
def attach_file(self, task_id: str, filepath: str) -> dict[str, Any]:
    url = f"{self.base_url}/WorkItems('{task_id}')/Attachments"
    # использует self._request("POST", url, files=...)
```

## Модель Task

```python
from tracker_assistant.models import Task

task = Task(
    project_id="uuid",          # обязательно
    summary="Название",         # обязательно
    description="...",          # опционально
    task_type="uuid",           # typeId в API
    assignee="user-uuid",       # assigneeId в API
    tags=["tag-uuid1"],         # список UUID тегов
    comments=["текст"],         # добавляются после create
    attachments=["path/file"],  # прикрепляются после create
    extra={"customField": val}, # произвольные поля API
)
```

`Task.to_api_body()` преобразует в тело запроса.  
`Task.from_dict(data)` создаёт из JSON-файла (лишние ключи игнорируются).

## Pipeline

```python
# Правильный паттерн функции pipeline
def list_something(adapter: TimettaAdapter) -> list[dict[str, Any]]:
    logger.debug("list_something: fetching")
    result = adapter.get_something()
    logger.debug("list_something: returned %d items", len(result))
    return result
```

Порядок в `create_task`:
1. `adapter.create_task(task)` → получить `task_id`
2. Добавить комментарии (`task.comments`)
3. Прикрепить файлы (`task.attachments`)

## CLI-команды

Паттерн новой команды:

```python
def cmd_new_action(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    adapter = _build_adapter(root)
    # логика
    result = do_something(adapter, ...)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
```

Регистрация:
```python
# В main():
new_p = sub.add_parser("new-action", help="Описание")
new_p.add_argument("--required", required=True)

commands["new-action"] = cmd_new_action
```

## Кеширование (io_utils.load_cached)

```python
from tracker_assistant.io_utils import load_cached

# TTL 24 часа по умолчанию, файл cache/<key>.json
users = load_cached(root, "users", adapter.get_users, no_cache=args.no_cache)
tags  = load_cached(root, "tags",  adapter.get_tags,  no_cache=args.no_cache)
```

Добавлять `--no-cache` флаг для всех команд с кешированием:
```python
parser.add_argument("--no-cache", action="store_true", help="Bypass local cache")
```

## Обработка ошибок

| Ситуация | Паттерн |
|---|---|
| Токен не задан | `raise SystemExit("ERROR: set TIMETTA_TOKEN in .env")` |
| Файл не найден | `raise SystemExit(f"ERROR: file not found: {path}")` |
| Мягкий сбой | `logging.warning("...")` + возврат пустого результата |
| HTTP-ошибка | Пробрасывать из адаптера, ловить на CLI-уровне |

## Логирование

```python
logger = logging.getLogger(__name__)

# DEBUG: вход в метод, ID запроса, промежуточные данные
logger.debug("create_task: project=%s summary=%r", task.project_id, task.summary)

# WARNING: нештатные ситуации без остановки
logger.warning("update: no fields specified for task %s", args.issue)
```

## Подробнее

- [Полный справочник API и OData-запросов](references/api-reference.md)
