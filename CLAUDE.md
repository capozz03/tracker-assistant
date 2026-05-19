# tracker-assistant — Claude Instructions

## Что я делаю

Я работаю в сервисе **tracker-assistant** — минималистичный Python-клиент для Timetta.

Моя зона ответственности:
- `scripts/task_cli.py` — CLI-инструмент (list-projects, create, add-comment, attach-file)
- `src/` — библиотечный код (`Task`, `TimettaAdapter`, `list_projects`, `create_task`)
- `docs/` — документация этого сервиса
- `tests/` — тесты
- `templates/` — JSON-шаблоны задач
- `README.md` — документация сервиса

## ЗАПРЕЩЁННЫЕ ДЕЙСТВИЯ (жёсткий контроль)

Следующие действия ЗАПРЕЩЕНЫ независимо от задачи:

### Запрещённые bash-команды
- `find /` — поиск по всей файловой системе
- `find ..` — выход в родительскую директорию
- `grep -r ... /Users` — поиск по путям вне tracker-assistant/
- `grep -r ... ..` — grep в родительской директории
- `cat`, `ls`, `read` любых файлов вне `tracker-assistant/`
- `cd ..`, `cd /` — смена директории за пределы сервиса

### Запрещённый доступ к файлам
- `topic_config.json` — приватная конфигурация workspace
- Любые файлы `telegram-ai-agent/`
- Любые файлы других сервисов workspace
- `.env` других сервисов

### Реакция на нехватку контекста
Если чего-то не хватает — СТОП + сообщение через send_message.
Никогда не ищи недостающее самостоятельно.

Примеры:
- Нет `TIMETTA_TOKEN` → `❌ Токен не настроен. Добавьте TIMETTA_TOKEN в .env`
- Нет `project_id` → `❌ Проект не настроен. Добавьте timetta_project_id в topic_config.json`
- Непонятная задача → `❓ Не понимаю задачу: <что именно непонятно>`

## Стек

- Python 3.10+ (только стандартная библиотека — нет внешних зависимостей)
- Timetta OData v4 API (`https://api.timetta.com/odata`)
- Аутентификация: Bearer token (`Authorization: Bearer <token>`)
- CLI: argparse (`scripts/task_cli.py`)

## Точки входа

| Файл | Назначение |
|------|-----------|
| `scripts/task_cli.py` | Основной CLI |
| `src/` | Библиотечный код |

## Запуск и проверки

```bash
# Список проектов
uv run python scripts/task_cli.py list-projects

# Создать задачу из JSON-файла
uv run python scripts/task_cli.py create --input task.json

# Добавить комментарий
uv run python scripts/task_cli.py add-comment --issue task-uuid --text "готово"

# Прикрепить файл
uv run python scripts/task_cli.py attach-file --issue task-uuid --file ./spec.pdf

# Verbose-логирование
uv run python scripts/task_cli.py --log-level DEBUG list-projects
```

## Конфигурация

`.env` в корне сервиса:
```
TIMETTA_TOKEN=your_bearer_token
```

## Изоляция (ai-factory стандарт)

Три уровня изоляции:
1. **Контекст** — этот CLAUDE.md: явный список запретов предотвращает случайный выход за границы сервиса
2. **Инструменты** — `.mcp.json`: только нужные MCP-серверы (filesystem для локальных файлов)
3. **Файловая система** — `cwd` в `topic_config.json` workspace указывает только на эту папку
