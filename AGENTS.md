# AGENTS.md

> Этот файл — структурная карта проекта для AI-агентов и новых разработчиков.
> Обновляйте при значительных изменениях структуры. Детальное содержание — в `.ai-factory/DESCRIPTION.md`.

## Обзор проекта

Минималистичный Python-клиент для Timetta — сервиса управления задачами.
Предоставляет CLI-инструмент и библиотечный API для работы с задачами через Timetta OData v4.

## Технологический стек

- **Язык программирования:** Python 3.10+
- **CLI:** argparse (стандартная библиотека)
- **Менеджер пакетов:** uv + hatchling
- **Тестирование:** pytest
- **Внешний API:** Timetta OData v4

## Структура проекта

```
tracker-assistant/
├── scripts/
│   ├── task_cli.py           # Основная точка входа CLI (argparse)
│   └── enrich_task.py        # Обогащение задачи через claude -p (теги, исполнитель)
├── src/
│   └── tracker_assistant/
│       ├── __init__.py       # Публичный API библиотеки
│       ├── models.py         # Модель Task (dataclass)
│       ├── pipeline.py       # Бизнес-логика (list_projects, create_task)
│       ├── io_utils.py       # Утилиты: .env, JSON, TTL-кеш
│       └── adapters/
│           └── timetta_adapter.py  # HTTP-клиент Timetta API
├── tests/
│   ├── test_adapter.py       # Тесты адаптера
│   ├── test_cache.py         # Тесты кеша
│   └── test_pipeline.py      # Тесты pipeline
├── templates/
│   └── task-default.json     # Шаблон задачи для CLI
├── docs/
│   ├── getting-started.md    # Установка и первый запуск
│   └── api-reference.md      # Справочник: Task, адаптер, task.json
├── .ai-factory/
│   ├── DESCRIPTION.md        # Спецификация проекта
│   ├── ARCHITECTURE.md       # Архитектурные решения
│   ├── config.yaml           # Конфигурация AI Factory
│   └── rules/
│       └── base.md           # Базовые конвенции кодовой базы
├── .env                      # TIMETTA_TOKEN (не коммитить)
├── .env.example              # Шаблон переменных окружения
├── pyproject.toml            # Зависимости и сборка
├── CLAUDE.md                 # Инструкции для агента + запреты
└── AGENTS.md                 # Этот файл
```

## Ключевые точки входа

| Файл | Назначение |
|---|---|
| [scripts/task_cli.py](scripts/task_cli.py) | CLI: list-projects, create, add-comment, attach-file, update, list-users, list-tags |
| [scripts/enrich_task.py](scripts/enrich_task.py) | Обогащение сырой задачи через `claude -p`: теги, исполнитель, описание → task.json |
| [src/tracker_assistant/__init__.py](src/tracker_assistant/__init__.py) | Публичный API: `Task`, `TimettaAdapter`, `list_projects`, `create_task` |
| [src/tracker_assistant/adapters/timetta_adapter.py](src/tracker_assistant/adapters/timetta_adapter.py) | HTTP-клиент Timetta OData v4 API |
| [src/tracker_assistant/pipeline.py](src/tracker_assistant/pipeline.py) | Оркестрация операций с задачами |
| [src/tracker_assistant/models.py](src/tracker_assistant/models.py) | Модель данных Task |
| [src/tracker_assistant/io_utils.py](src/tracker_assistant/io_utils.py) | Загрузка .env, TTL-кеш для users/tags |
| [pyproject.toml](pyproject.toml) | Зависимости, точки входа `task-cli`, `enrich-task` |

## Документация

| Документ | Путь | Описание |
|---|---|---|
| README | [README.md](README.md) | Быстрый старт, примеры CLI, ссылки на доки |
| Начало работы | [docs/getting-started.md](docs/getting-started.md) | Установка, настройка .env, первый запуск |
| API-справочник | [docs/api-reference.md](docs/api-reference.md) | Task, адаптер, формат task.json |

## AI-контекстные файлы

| Файл | Назначение |
|---|---|
| [AGENTS.md](AGENTS.md) | Этот файл — карта проекта для агентов |
| [.ai-factory/DESCRIPTION.md](.ai-factory/DESCRIPTION.md) | Детальная спецификация проекта и стека |
| [.ai-factory/ARCHITECTURE.md](.ai-factory/ARCHITECTURE.md) | Архитектурные решения, правила зависимостей, паттерны Layered Architecture |
| [.ai-factory/rules/base.md](.ai-factory/rules/base.md) | Базовые конвенции кодовой базы |
| [CLAUDE.md](CLAUDE.md) | Инструкции для агента: зона ответственности, запреты |

## Правила для агентов

- Команды выполнять по одной, не объединять в цепочки:
  - Неправильно: `git checkout main && git pull`
  - Правильно: сначала `git checkout main`, затем `git pull origin main`
- Работать только внутри директории `tracker-assistant/` — выход запрещён
- При отсутствии `TIMETTA_TOKEN` — немедленный стоп с сообщением об ошибке
- Никогда не читать файлы других сервисов workspace
