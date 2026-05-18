[Back to README](../README.md) · [API-справочник →](api-reference.md)

# Начало работы

## Требования

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) — менеджер пакетов и окружений
- Токен OAuth для Yandex Tracker
- Org ID организации (Cloud или Yandex)

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
YANDEX_TRACKER_TOKEN=AgAAAABx...
YANDEX_TRACKER_ORG_ID=12345678
# Необязательно (default: cloud)
# YANDEX_TRACKER_ORG_TYPE=cloud
```

| Переменная | Обязательна | Описание |
|---|---|---|
| `YANDEX_TRACKER_TOKEN` | да | OAuth-токен Yandex |
| `YANDEX_TRACKER_ORG_ID` | да | ID организации |
| `YANDEX_TRACKER_ORG_TYPE` | нет | `cloud` (default) или `yandex` |

**Где взять токен:** Yandex OAuth → приложения → получить токен с правами Tracker.

**Где взять Org ID:** Yandex Cloud → организация → ID, или из URL Tracker (`tracker.yandex.ru/org/<ID>`).

**`org_type`:** используйте `cloud` для Cloud Organization (X-Cloud-Org-ID), `yandex` для Yandex Organization (X-Org-ID).

## Первый запуск

```bash
# Проверить подключение — получить список проектов
uv run python scripts/task_cli.py list-projects
```

Ожидаемый вывод:
```json
[
  { "id": "1", "name": "Мой проект", "shortName": "MYPROJ" },
  ...
]
```

Если получили ошибку — проверьте токен и org_id в `.env`.

## Создание задачи

### 1. Подготовьте task.json

```json
{
  "queue": "MYPROJ",
  "summary": "Добавить API для подтверждения заказа",
  "description": "## Контекст\n\nПокупатель подтверждает заказ.",
  "issue_type": "task",
  "tags": ["backend", "api"],
  "assignee": "ivanov",
  "followers": ["petrov"],
  "comments": ["Обсудить на стендапе"],
  "attachments": []
}
```

### 2. Создайте задачу

```bash
uv run python scripts/task_cli.py create --input task.json
```

Вывод — полный JSON ответа от API, включая ключ созданной задачи:

```json
{ "key": "MYPROJ-42", "summary": "Добавить API для подтверждения заказа", ... }
```

## Добавление комментария

```bash
uv run python scripts/task_cli.py add-comment --issue MYPROJ-42 --text "Реализовано, готово к ревью"
```

## Прикрепление файла

```bash
uv run python scripts/task_cli.py attach-file --issue MYPROJ-42 --file ./docs/spec.pdf
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
