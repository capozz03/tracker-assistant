[Back to README](../README.md) · [API-справочник →](api-reference.md)

# Начало работы

## Требования

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) — менеджер пакетов и окружений
- Bearer-токен Timetta (OAuth 2.0)

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
```

| Переменная | Обязательна | Описание |
|---|---|---|
| `TIMETTA_TOKEN` | да | Bearer-токен Timetta (OAuth 2.0) |

**Где взять токен:** Timetta → настройки аккаунта → API → создать токен доступа.

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
  "summary": "Добавить API для подтверждения заказа",
  "description": "## Контекст\n\nПокупатель подтверждает заказ.",
  "tags": ["backend", "api"],
  "assignee": "user-uuid",
  "comments": ["Обсудить на стендапе"],
  "attachments": []
}
```

### 2. Создайте задачу

```bash
uv run python scripts/task_cli.py create --input task.json
```

Вывод — полный JSON ответа от API, включая id созданной задачи:

```json
{ "id": "task-uuid-42", "name": "Добавить API для подтверждения заказа", ... }
```

## Добавление комментария

```bash
uv run python scripts/task_cli.py add-comment --issue task-uuid-42 --text "Реализовано, готово к ревью"
```

## Прикрепление файла

```bash
uv run python scripts/task_cli.py attach-file --issue task-uuid-42 --file ./docs/spec.pdf
```

## Отладочный режим

```bash
uv run python scripts/task_cli.py --log-level DEBUG list-projects
```

В DEBUG-режиме все HTTP-запросы к API логируются: метод, путь, тело запроса, статус ответа.

## Передача --root

По умолчанию `.env` ищется в текущей директории. Если запускаете CLI из другого места:

```bash
uv run python /path/to/scripts/task_cli.py --root /path/to/tracker-assistant list-projects
```

## Запуск тестов

```bash
uv run pytest tests/ -v
```

## See Also

- [API-справочник](api-reference.md) — Task dataclass, методы адаптера, формат task.json
- [README](../README.md) — обзор проекта
