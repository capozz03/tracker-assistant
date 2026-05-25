[Back to README](../README.md) · [Submit Pipeline →](submit-pipeline.md)

# Начало работы

## Требования

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) — менеджер пакетов и окружений
- Bearer-токен Timetta

## Установка

Клонируйте репозиторий или скопируйте папку `tracker-assistant`. Внешних runtime-зависимостей нет — только стандартная библиотека Python.

```bash
git clone <repo-url> tracker-assistant
cd tracker-assistant

# Создать виртуальное окружение и установить зависимости
uv sync
```

## Настройка .env

Создайте файл `.env` в корне `tracker-assistant/`:

```env
TIMETTA_TOKEN=your_bearer_token
TIMETTA_PROJECT_ID=your_project_uuid
```

| Переменная | Обязательна | Описание |
|---|---|---|
| `TIMETTA_TOKEN` | да | Bearer-токен Timetta |
| `TIMETTA_PROJECT_ID` | нет | UUID проекта по умолчанию (для `task-submit` и `task-telegram` без `telegram_projects.json`) |
| `TIMETTA_TAGS_DIR_ID` | нет | ID директории тегов (дефолт работает для стандартных инстансов) |

**Где взять токен:** Timetta → Настройки аккаунта → API → создать токен доступа.

**Где взять project-id:**
```bash
uv run python scripts/task_cli.py list-projects
```

## Первый запуск

```bash
# Проверить подключение — получить список проектов
uv run python scripts/task_cli.py list-projects
```

Ожидаемый вывод:
```json
[
  { "id": "uuid-1", "name": "Мой проект", "code": "MYPROJ" },
  ...
]
```

Если получили ошибку — проверьте токен в `.env`.

## Создание задачи

### 1. Подготовьте task.json

```json
{
  "project_id": "your-project-uuid",
  "task_type": "968f71c6-6b38-4845-963a-b2d07ec95185",
  "summary": "Добавить API для подтверждения заказа",
  "description": "## Контекст\n\nПокупатель подтверждает заказ.",
  "assignee": "user-uuid",
  "comments": ["Обсудить на стендапе"],
  "attachments": []
}
```

> **Важно:** `task_type` обязателен для Timetta. Дефолтное значение: `968f71c6-6b38-4845-963a-b2d07ec95185`.

### 2. Создайте задачу

```bash
uv run python scripts/task_cli.py create --input task.json
```

Вывод — полный JSON ответа от API, включая id созданной задачи.

## Авто-создание задач из требований (submit_task.py)

Полный конвейер: текст → анализ стека → Claude → создание задач с тегами и спринтом.

```bash
# Из файла требований
uv run python scripts/submit_task.py \
  --requirements-file tasks.md \
  --project-id <uuid> \
  --sprint-id <sprint-uuid>

# Текст напрямую + анализ кодовой базы
uv run python scripts/submit_task.py \
  --requirements "Добавить мультиселект регионов" \
  --project-path /path/to/your/project
```

Claude автоматически разбивает задачи на Frontend/Backend и проставляет теги. Подробнее → [Submit Pipeline](submit-pipeline.md).

## Обновление задачи (теги, исполнитель)

```bash
# Назначить исполнителя
uv run python scripts/task_cli.py update --issue <task-id> --assignee <user-uuid>

# Установить теги
uv run python scripts/task_cli.py update --issue <task-id> --set-tags <tag-uuid1>,<tag-uuid2>

# Добавить один тег (сохраняет существующие)
uv run python scripts/task_cli.py update --issue <task-id> --add-tag <tag-uuid>
```

## Добавление комментария и файла

```bash
uv run python scripts/task_cli.py add-comment --issue task-uuid --text "Реализовано, готово к ревью"
uv run python scripts/task_cli.py attach-file --issue task-uuid --file ./docs/spec.pdf
```

## Отладочный режим

```bash
uv run python scripts/task_cli.py --log-level DEBUG list-projects
```

В DEBUG-режиме все HTTP-запросы к API логируются: метод, путь, тело запроса, статус ответа.

## Список пользователей и тегов

```bash
uv run python scripts/task_cli.py list-users
uv run python scripts/task_cli.py list-tags

# Сбросить кеш (TTL 24 ч)
uv run python scripts/task_cli.py list-tags --no-cache
```

## Запуск тестов

```bash
uv run pytest tests/ -v
```

## Telegram Bot (`task-telegram`)

Запуск бота для управления задачами через Telegram:

1. Добавьте в `.env`:
   ```env
   TELEGRAM_TOKEN=your_bot_token_from_botfather
   ```
2. Запустите:
   ```bash
   uv run task-telegram
   ```
3. Отправьте боту текст с требованиями — он создаст задачи и ответит ссылками.

Подробности — [Telegram Bot](telegram-bot.md).

## See Also

- [Submit Pipeline](submit-pipeline.md) — авто-создание задач из требований
- [API-справочник](api-reference.md) — Task dataclass, методы адаптера, форматы
- [Timetta API: нюансы](timetta-quirks.md) — подводные камни и нюансы интеграции
- [Telegram Bot](telegram-bot.md) — бот для управления задачами через Telegram
