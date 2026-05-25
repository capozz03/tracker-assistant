# Архитектура: Structured Modules (Technical Layers)

## Обзор

tracker-assistant использует **Structured Modules** — модульную архитектуру, где каждый модуль инкапсулирует свою предметную область с собственными моделями, сервисом и адаптером. Паттерн выбран как переход от текущего нарушенного Layered Architecture: скрипты выросли до 500+ строк и содержат application-логику, а `_call_claude` продублирован в двух файлах.

Каждый модуль имеет **публичный API** (`__init__.py`) — снаружи виден только он. Скрипты становятся тонкими CLI-обёртками (~50 строк): читают аргументы, вызывают `module.service.do_thing()`, печатают результат.

## Обоснование выбора

- **Тип проекта:** CLI-инструмент / Python-библиотека с тремя независимыми фичами
- **Стек:** Python 3.10+, stdlib only, argparse, pytest
- **Ключевой фактор:** Три независимых bounded context (task management, submit pipeline, enrichment) с общим LLM-клиентом — точное соответствие паттерну Structured Modules

## Целевая структура папок

```
tracker-assistant/
│
├── scripts/                               # [Presentation] Тонкие CLI-обёртки (~50 строк каждый)
│   ├── task_cli.py                        # CLI → timetta.service
│   ├── submit_task.py                     # CLI → submit.service
│   └── enrich_task.py                     # CLI → enrich.service
│
├── src/
│   └── tracker_assistant/
│       ├── __init__.py                    # Публичный API пакета (re-exports)
│       │
│       ├── timetta/                       # МОДУЛЬ: управление задачами
│       │   ├── __init__.py                # Публичный API: Task, TimettaAdapter, list_projects, create_task
│       │   ├── models.py                  # Task dataclass (to_api_body, from_dict)
│       │   ├── adapter.py                 # TimettaAdapter — единственный HTTP-клиент Timetta
│       │   └── service.py                 # list_projects, create_task (оркестрация)
│       │
│       ├── submit/                        # МОДУЛЬ: создание задач из требований
│       │   ├── __init__.py                # Публичный API: submit_requirements
│       │   ├── stack_detector.py          # scan_project_stack, _build_stack_context
│       │   ├── prompt.py                  # _PROMPT_TEMPLATE, _build_prompt, _resolve_tags
│       │   └── service.py                 # submit_requirements (главный оркестратор)
│       │
│       ├── enrich/                        # МОДУЛЬ: обогащение задач через LLM
│       │   ├── __init__.py                # Публичный API: enrich_task
│       │   └── service.py                 # enrich_task logic
│       │
│       └── shared/                        # Общие утилиты (cross-cutting)
│           ├── io_utils.py                # load_env, load_cached, read/write_json
│           └── claude_client.py           # _call_claude (один экземпляр для submit и enrich)
│
├── tests/
│   ├── test_timetta_adapter.py            # Зеркало: timetta/adapter.py
│   ├── test_timetta_service.py            # Зеркало: timetta/service.py
│   ├── test_submit_stack.py               # Зеркало: submit/stack_detector.py
│   ├── test_submit_service.py             # Зеркало: submit/service.py
│   ├── test_enrich_service.py             # Зеркало: enrich/service.py
│   ├── test_claude_client.py              # Зеркало: shared/claude_client.py
│   └── test_cache.py                      # Зеркало: shared/io_utils.py
│
├── docs/
├── templates/
└── cache/                                 # Runtime-кеш (gitignore)
```

## Правила зависимостей

```
scripts/                    [Presentation]
  task_cli.py    ──→  tracker_assistant.timetta
  submit_task.py ──→  tracker_assistant.submit
  enrich_task.py ──→  tracker_assistant.enrich

tracker_assistant.timetta   [Модуль]
  service.py     ──→  timetta.adapter, timetta.models

tracker_assistant.submit    [Модуль]
  service.py     ──→  submit.stack_detector, submit.prompt
                 ──→  tracker_assistant.timetta (публичный API)
                 ──→  shared.claude_client, shared.io_utils

tracker_assistant.enrich    [Модуль]
  service.py     ──→  shared.claude_client, shared.io_utils
                 ──→  tracker_assistant.timetta (публичный API)

tracker_assistant.shared    [Cross-cutting]
  (нет зависимостей на другие модули проекта)
```

- ✅ Скрипты импортируют только публичный API модуля (`from tracker_assistant.submit import submit_requirements`)
- ✅ Модули зависят от `shared/` и могут использовать публичный API других модулей
- ✅ `shared/` не зависит ни от одного модуля
- ❌ Скрипты не импортируют внутренности модуля (например, `submit.prompt._PROMPT_TEMPLATE`)
- ❌ Модули не импортируют из скриптов
- ❌ `shared/` не импортирует из `timetta/`, `submit/`, `enrich/`
- ❌ Circular imports между модулями

## Публичные API модулей

Каждый `__init__.py` явно декларирует, что видно снаружи:

```python
# tracker_assistant/timetta/__init__.py
from .models import Task
from .adapter import TimettaAdapter
from .service import list_projects, create_task

__all__ = ["Task", "TimettaAdapter", "list_projects", "create_task"]
```

```python
# tracker_assistant/submit/__init__.py
from .service import submit_requirements

__all__ = ["submit_requirements"]
```

```python
# tracker_assistant/enrich/__init__.py
from .service import enrich_task

__all__ = ["enrich_task"]
```

## Коммуникация между модулями

- **Синхронные вызовы функций** — прямые вызовы через публичный API (`timetta.service.create_task`)
- **Инъекция адаптера** — `TimettaAdapter` создаётся в скрипте (`_build_adapter`) и передаётся в service как аргумент
- **Общий LLM-клиент** — `shared.claude_client._call_claude` используется и в `submit`, и в `enrich`
- Нет событий, нет очередей, нет глобального состояния

## Ключевые принципы

1. **Один скрипт — один модуль** — каждый CLI-скрипт вызывает ровно один модуль. Логика выбора, что делать — в модуле, не в скрипте.
2. **Тонкие скрипты** — скрипт: парсинг аргументов → вызов `module.service.do_thing()` → вывод. Не более ~50-80 строк.
3. **`shared/` остаётся маленьким** — только `io_utils` и `claude_client`. Если появляется третий файл — проверь, не принадлежит ли он модулю.
4. **Нет дублирования** — `_call_claude` существует в одном месте: `shared/claude_client.py`. `_build_adapter` — в одном месте (скрипт или shared-утилита).
5. **Публичный API = единственная точка входа** — внешний код видит только `__init__.py` модуля.

## Примеры кода

### Тонкий CLI-скрипт (submit_task.py после рефакторинга)

```python
# scripts/submit_task.py — только presentation (~60 строк)
import argparse, json, sys
from pathlib import Path
from tracker_assistant.submit import submit_requirements
from tracker_assistant.shared.io_utils import load_env, load_cached
from tracker_assistant.timetta import TimettaAdapter

def _build_adapter(root: Path) -> TimettaAdapter:
    env = load_env(root)
    token = env.get("TIMETTA_TOKEN") or os.environ.get("TIMETTA_TOKEN", "")
    if not token:
        raise SystemExit("ERROR: TIMETTA_TOKEN не задан")
    return TimettaAdapter(token=token)

def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    adapter = _build_adapter(root)
    users = load_cached(root, "users", adapter.get_users)
    tags  = load_cached(root, "tags",  adapter.get_tags)

    results = submit_requirements(          # ← вся логика в модуле
        requirements=args.requirements,
        project_id=args.project_id,
        adapter=adapter,
        users=users,
        tags=tags,
        project_path=Path(args.project_path) if args.project_path else None,
        sprint_id=args.sprint_id or "",
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0
```

### Внутри модуля submit (service.py)

```python
# tracker_assistant/submit/service.py — application logic
from ..timetta import create_task, Task
from ..shared.io_utils import load_env
from ..shared.claude_client import call_claude
from .stack_detector import scan_project_stack, build_stack_context
from .prompt import build_prompt, resolve_tags

def submit_requirements(
    requirements: str,
    project_id: str,
    adapter,            # TimettaAdapter — передаётся снаружи
    users: list[dict],
    tags: list[dict],
    project_path: Path | None,
    sprint_id: str = "",
) -> list[dict]:
    stack = scan_project_stack(project_path) if project_path else _empty_stack()
    prompt = build_prompt(requirements, stack, tags, users, project_id)
    task_dicts = call_claude(prompt)         # ← shared
    return _create_tasks(adapter, task_dicts, tags, project_id, sprint_id)
```

### Добавление нового модуля (пример: webhooks)

```python
# 1. Создать tracker_assistant/webhooks/
#    __init__.py, service.py, models.py

# 2. tracker_assistant/webhooks/__init__.py
from .service import register_webhook, list_webhooks
__all__ = ["register_webhook", "list_webhooks"]

# 3. scripts/webhooks_cli.py — тонкий CLI
from tracker_assistant.webhooks import register_webhook
```

## Миграция из текущего состояния

| Откуда (сейчас) | Куда (целевое) |
|---|---|
| `scripts/submit_task.py` → `scan_project_stack`, `_build_stack_context` | `submit/stack_detector.py` |
| `scripts/submit_task.py` → `_PROMPT_TEMPLATE`, `_resolve_tags` | `submit/prompt.py` |
| `scripts/submit_task.py` → `submit_requirements` | `submit/service.py` |
| `scripts/submit_task.py` → `_call_claude` | `shared/claude_client.py` |
| `scripts/enrich_task.py` → `_call_claude` (дубликат) | `shared/claude_client.py` (один) |
| `scripts/enrich_task.py` → логика обогащения | `enrich/service.py` |
| `src/tracker_assistant/models.py` | `timetta/models.py` |
| `src/tracker_assistant/pipeline.py` | `timetta/service.py` |
| `src/tracker_assistant/adapters/timetta_adapter.py` | `timetta/adapter.py` |
| `src/tracker_assistant/io_utils.py` | `shared/io_utils.py` |

## Анти-паттерны

- ❌ Скрипт > 100 строк — значит в нём есть логика, которой там не место
- ❌ `from tracker_assistant.submit.prompt import _PROMPT_TEMPLATE` снаружи модуля — обращение к внутренностям
- ❌ `_call_claude` в двух местах — всё через `shared/claude_client`
- ❌ `shared/` растёт: появился третий файл → скорее всего это признак нового модуля
- ❌ Модуль `submit` импортирует из `enrich` — если нужна общая логика, выноси в `shared/`
- ❌ Бизнес-логика в скрипте (if/else, преобразование данных) — только в service.py модуля
