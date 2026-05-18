# tracker-assistant — Claude Instructions

## Что я делаю

Я работаю в сервисе **tracker-assistant** — минималистичный Python-клиент для Yandex Tracker.

Моя зона ответственности:
- `scripts/task_cli.py` — CLI-инструмент (list-projects, create, add-comment, attach-file)
- `src/` — библиотечный код (`Task`, `YandexTrackerAdapter`, `list_projects`, `create_task`)
- `docs/` — документация этого сервиса
- `tests/` — тесты
- `templates/` — JSON-шаблоны задач
- `README.md` — документация сервиса

## Что я НЕ делаю

- НЕ трогаю файлы за пределами `tracker-assistant/`
- НЕ читаю и НЕ изменяю `topic_config.json` в корне workspace
- НЕ знаю о `telegram-ai-agent` и не помогаю с его кодом
- НЕ изменяю `Makefile` корневого workspace
- НЕ изменяю `services.yaml` и другие файлы оркестрации workspace
- НЕ работаю с другими сервисами workspace

## Стек

- Python 3.10+ (только стандартная библиотека — нет внешних зависимостей)
- Yandex Tracker REST API (OAuth-токен + Org ID)
- CLI: argparse (`scripts/task_cli.py`)

## Точки входа

| Файл | Назначение |
|------|-----------|
| `scripts/task_cli.py` | Основной CLI |
| `src/` | Библиотечный код |

## Запуск и проверки

```bash
# Список проектов
python scripts/task_cli.py list-projects

# Создать задачу из JSON-файла
python scripts/task_cli.py create --input task.json

# Добавить комментарий
python scripts/task_cli.py add-comment --issue PROJ-123 --text "готово"

# Прикрепить файл
python scripts/task_cli.py attach-file --issue PROJ-123 --file ./spec.pdf

# Verbose-логирование
python scripts/task_cli.py --log-level DEBUG list-projects
```

## Конфигурация

`.env` в корне сервиса:
```
YANDEX_TRACKER_TOKEN=your_oauth_token
YANDEX_TRACKER_ORG_ID=your_org_id
```

## Изоляция (ai-factory стандарт)

Три уровня изоляции:
1. **Контекст** — этот CLAUDE.md: явный список запретов предотвращает случайный выход за границы сервиса
2. **Инструменты** — `.mcp.json`: только нужные MCP-серверы (filesystem для локальных файлов)
3. **Файловая система** — `cwd` в `topic_config.json` workspace указывает только на эту папку
