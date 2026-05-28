[← Начало работы](getting-started.md) · [Back to README](../README.md) · [Telegram Bot →](telegram-bot.md)

# Submit Pipeline — авто-создание задач из требований

`scripts/submit_task.py` — полный конвейер: текст требований → анализ кодовой базы → разбивка по слоям → создание задач в Timetta.

---

## Быстрый старт

```bash
# Из файла требований
uv run python scripts/submit_task.py \
  --requirements-file tasks.md \
  --project-id 6d6e852f-59c3-4a49-bd7f-3782faa82ef1 \
  --sprint-id 941a82f6-7f26-4ecb-af63-2f2f5ba02b91

# Из текста напрямую
uv run python scripts/submit_task.py \
  --requirements "Добавить мультиселект регионов в фильтры" \
  --project-id <uuid>

# С анализом кодовой базы
uv run python scripts/submit_task.py \
  --requirements-file tasks.md \
  --project-path /path/to/your/project \
  --project-id <uuid>
```

---

## Как работает конвейер

```
Требования (текст / файл / stdin)
        ↓
1. scan_project_stack(project_path)
   → {has_frontend, has_backend, technologies, description}
        ↓
2. claude -p [стек + теги + исполнители + требования]
   → JSON-массив задач (разбивка Frontend / Backend)
        ↓
3. Для каждой задачи:
   POST /odata/Issues  (typeId, sprintId, name, description)
        ↓
   PATCH /odata/Issues(uuid) { tags: [...DirectorySetEntry] }
        ↓
4. Вывод: id, summary, tags, url
```

**Разбивка по слоям:** если задача затрагивает и фронтенд, и бэкенд — Claude создаёт две задачи с соответствующими тегами. Если только один слой — одна задача.

---

## CLI-аргументы

| Аргумент | Обязательный | Описание |
|---|---|---|
| `--requirements "текст"` | один из трёх | Текст требований напрямую |
| `--requirements-file path` | один из трёх | Путь к файлу (.md/.txt) |
| stdin | один из трёх | Требования из stdin |
| `--project-id uuid` | да* | UUID проекта в Timetta |
| `--sprint-id uuid` | нет | UUID спринта (добавляет `sprintId` к задачам) |
| `--project-path path` | нет | Путь к анализируемой кодовой базе |
| `--root path` | нет | Корень tracker-assistant (где `.env`) |
| `--no-cache` | нет | Игнорировать кеш тегов/пользователей |
| `--log-level` | нет | DEBUG / INFO / WARNING / ERROR |

*Или `TIMETTA_PROJECT_ID` в `.env`

---

## Анализ стека (scan_project_stack)

Лёгкое сканирование файлового дерева (глубина ≤ 3, лимит 500 файлов):

| Источник | Что определяет |
|---|---|
| `next.config.js`, `vite.config.ts`, `angular.json` | Frontend-фреймворк |
| `pyproject.toml`, `requirements.txt`, `go.mod` | Backend-язык |
| Директории `frontend/`, `api/`, `backend/`, `web/` | Слой проекта |
| `package.json` зависимости | React, Vue, Express, NestJS… |
| Расширения `.tsx/.jsx/.vue` / `.py/.go/.java` | Слой по файлам |
| `README.md` (первые 800 символов) | Описание проекта |

Пропускает: `node_modules`, `.git`, `__pycache__`, `dist`, `build`, `.next`.

---

## Подключение к другому проекту

Для каждого нового проекта достаточно передать `--project-path` и `--project-id`:

```bash
# Проект А (туристический маркетплейс)
uv run python scripts/submit_task.py \
  --requirements-file /path/to/ahhu/tasks.md \
  --project-path /path/to/ahhu-tour \
  --project-id 6d6e852f-59c3-4a49-bd7f-3782faa82ef1

# Проект Б (другой проект)
uv run python scripts/submit_task.py \
  --requirements "Добавить авторизацию" \
  --project-path /path/to/project-b \
  --project-id <project-b-uuid>
```

Для постоянного проекта — пропиши `TIMETTA_PROJECT_ID` в `.env`.

---

## Формат вывода

```json
[
  {
    "id": "6f623165-...",
    "summary": "Frontend: UI полнотекстового поиска",
    "tags": ["c98cabfb-..."],
    "assignee": "",
    "url": "https://app.timetta.com/issues/6f623165-..."
  },
  {
    "id": "137e39f8-...",
    "summary": "Backend: Логика полнотекстового поиска",
    "tags": ["e9967692-...", "715ce557-..."],
    "assignee": "",
    "url": "https://app.timetta.com/issues/137e39f8-..."
  }
]
```

В stderr выводится читаемый итог:

```
✅ Создано задач: 2
  • Frontend: UI полнотекстового поиска
    https://app.timetta.com/issues/6f623165-...
  • Backend: Логика полнотекстового поиска
    https://app.timetta.com/issues/137e39f8-...
```

---

## Получить sprint-id и project-id

```bash
# Список проектов
uv run python scripts/task_cli.py list-projects

# Список спринтов (через адаптер напрямую)
uv run python -c "
import sys, urllib.parse; sys.path.insert(0, 'src')
from tracker_assistant.io_utils import load_env
from tracker_assistant.adapters.timetta_adapter import TimettaAdapter
import json
env = load_env(__import__('pathlib').Path('.'))
a = TimettaAdapter(token=env['TIMETTA_TOKEN'])
r = a._request('GET', '/Sprints', params=urllib.parse.urlencode({
    '\$filter': 'isCurrent eq true', '\$select': 'id,name,startDate,endDate,viewId'
}))
print(json.dumps(r['value'], ensure_ascii=False, indent=2))
"
```

---

## Путь к Telegram-боту

Для интеграции в Telegram-бот достаточно одной команды:

```python
# В mode.md или обработчике сообщения
subprocess.run([
    "uv", "run", "python", "scripts/submit_task.py",
    "--requirements", message_text,
    "--project-path", topic_config["project_path"],
    "--project-id", topic_config["project_id"],
    "--sprint-id", topic_config.get("sprint_id", ""),
], cwd=tracker_assistant_root)
```

Параметры `project_path`, `project_id`, `sprint_id` хранятся в `topic_config.json` воркспейса.

## See Also

- [Начало работы](getting-started.md) — установка, настройка .env
- [API-справочник](api-reference.md) — методы адаптера, Task модель
- [Timetta API: нюансы](timetta-quirks.md) — форматы, ошибки, подводные камни
