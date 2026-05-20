# Архитектура: Layered Architecture

## Обзор

tracker-assistant использует трёхслойную архитектуру: слой представления (CLI), слой приложения (pipeline) и инфраструктурный слой (HTTP-адаптер). Паттерн выбран как наиболее подходящий для небольшого инструмента-клиента: простой домен, один разработчик, нулевые требования к масштабу, и существующая структура кода уже точно следует этому паттерну.

Ключевой принцип: бизнес-логика (pipeline) изолирована от транспорта (HTTP в адаптере) и от UI (argparse в CLI). Адаптер — единственная точка входа к Timetta API.

## Обоснование выбора

- **Тип проекта:** CLI-инструмент / Python-библиотека для Timetta API
- **Стек:** Python 3.10+, stdlib only, argparse, pytest
- **Ключевой фактор:** Проект уже имеет трёхслойную структуру — паттерн формализует существующее решение

## Структура папок

```
tracker-assistant/
├── scripts/
│   └── task_cli.py            # [Presentation] CLI: argparse, форматирование вывода
│
├── src/
│   └── tracker_assistant/
│       ├── __init__.py        # Публичный API библиотеки
│       ├── models.py          # [Domain] Модель Task (dataclass, to_api_body)
│       ├── pipeline.py        # [Application] Оркестрация: list_projects, create_task
│       ├── io_utils.py        # [Application] Утилиты: load_env, load_cached, read/write_json
│       └── adapters/
│           └── timetta_adapter.py  # [Infrastructure] HTTP-клиент Timetta OData v4
│
├── tests/                     # Зеркалирует src/ структуру
│   ├── test_adapter.py
│   ├── test_cache.py
│   └── test_pipeline.py
│
├── templates/
│   └── task-default.json      # Шаблоны задач для CLI
│
└── docs/                      # Документация
    ├── getting-started.md
    └── api-reference.md
```

## Правила зависимостей

```
[Presentation]     scripts/task_cli.py
       ↓  (импортирует)
[Application]      pipeline.py, io_utils.py
       ↓  (импортирует)
[Infrastructure]   adapters/timetta_adapter.py
[Domain]           models.py  ← не зависит ни от чего внешнего
```

- ✅ CLI импортирует pipeline и adapter напрямую (через `_build_adapter`)
- ✅ Pipeline импортирует adapter и models
- ✅ Adapter импортирует только models (для `Task`)
- ✅ Models не имеют внешних зависимостей
- ❌ Adapter не должен знать о CLI или pipeline
- ❌ Models не должны импортировать adapter или pipeline
- ❌ Pipeline не должен делать HTTP-запросы напрямую (только через adapter)

## Коммуникация между слоями

- **CLI → Application:** вызов функций pipeline (`list_projects`, `create_task`)
- **CLI → Infrastructure:** создание адаптера через `_build_adapter(root)`, передача в pipeline
- **Application → Infrastructure:** методы адаптера (`adapter.create_task(task)`)
- **Application → Domain:** создание и передача `Task` dataclass
- Нет событий, нет очередей — прямые вызовы функций

## Ключевые принципы

1. **Один путь к API** — все HTTP-запросы только через `TimettaAdapter`. CLI и pipeline не вызывают HTTP напрямую.
2. **Модели без зависимостей** — `Task` dataclass содержит только данные и простые преобразования (`to_api_body`, `from_dict`). Никаких импортов из других модулей проекта.
3. **Pipeline как оркестратор** — pipeline координирует последовательность операций (создать → добавить комментарии → прикрепить файлы), но не знает о транспорте.
4. **SystemExit для конфигурационных ошибок** — фатальные ошибки конфигурации (нет токена) вызывают `SystemExit`, не кастомные исключения.
5. **Кеш на уровне приложения** — `io_utils.load_cached` кеширует данные users/tags в `cache/`, обходя адаптер при повторных запросах.

## Примеры кода

### Добавление нового метода в адаптер

```python
# src/tracker_assistant/adapters/timetta_adapter.py

def get_task_types(self) -> list[dict[str, Any]]:
    """Получить список типов задач проекта."""
    url = f"{self.base_url}/WorkItemTypes"
    response = self._request("GET", url)
    return response.get("value", [])
```

### Добавление функции в pipeline

```python
# src/tracker_assistant/pipeline.py

def list_task_types(adapter: TimettaAdapter) -> list[dict[str, Any]]:
    logger.debug("list_task_types: fetching from API")
    types = adapter.get_task_types()
    logger.debug("list_task_types: returned %d types", len(types))
    return types
```

### Добавление CLI-команды

```python
# scripts/task_cli.py

def cmd_list_types(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    adapter = _build_adapter(root)
    types = load_cached(root, "task_types", adapter.get_task_types, no_cache=args.no_cache)
    print(json.dumps(types, ensure_ascii=False, indent=2))
    return 0

# В main():
types_p = sub.add_parser("list-types", help="Список типов задач")
types_p.add_argument("--no-cache", action="store_true")
commands["list-types"] = cmd_list_types
```

### Правильное использование модели Task

```python
# Создание из JSON-файла (CLI)
data = json.loads(input_path.read_text(encoding="utf-8"))
task = Task.from_dict(data)  # лишние ключи игнорируются

# Передача через слои
result = create_task(adapter, task, root=root)  # pipeline обрабатывает комментарии/вложения
```

## Анти-паттерны

- ❌ HTTP-запросы в pipeline или CLI (нарушает изоляцию слоёв)
- ❌ Импорт `TimettaAdapter` в `models.py` (нарушает правило независимости моделей)
- ❌ Бизнес-логика последовательности операций в адаптере (должна быть в pipeline)
- ❌ Прямое чтение `.env` в adapter (только через `io_utils.load_env` в `_build_adapter`)
- ❌ Кеш в адаптере (кеширование — ответственность io_utils на уровне приложения)
- ❌ Несколько адаптеров для одного API (один `TimettaAdapter` для всех операций)
