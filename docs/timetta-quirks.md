[← API-справочник](api-reference.md) · [Back to README](../README.md)

# Timetta API: нюансы и подводные камни

Задокументированные нюансы Timetta OData v4 API, выявленные в ходе интеграции. Раздел для тех, кто расширяет адаптер или строит новые интеграции.

---

## 1. Путь к задаче — UUID без кавычек

**Проблема.** Стандартный OData-путь строкового ключа выглядит как `/Issues('uuid')` — со строковыми кавычками. Timetta не принимает этот формат.

```http
# ❌ 404 Not Found
GET /odata/Issues('02ad466d-6399-4dc0-bf17-713b97fc1797')
PATCH /odata/Issues('02ad466d-6399-4dc0-bf17-713b97fc1797')

# ✅ Работает
GET /odata/Issues(02ad466d-6399-4dc0-bf17-713b97fc1797)
PATCH /odata/Issues(02ad466d-6399-4dc0-bf17-713b97fc1797)
```

**Правило:** всегда используй UUID без одиночных кавычек в пути.

---

## 2. Теги — Collection(WP.DirectorySetEntry)

**Проблема.** Поле `tags` имеет тип `Collection(WP.DirectorySetEntry)`. Передача строк-UUID вызывает ошибку 400 «NoDelta: Entity changes must be passed».

**Структура DirectorySetEntry** (из `$metadata`):

```
directoryEntryId  Edm.Guid   — UUID тега (из /DirectoryEntries)
directoryId       Edm.Guid   — UUID директории тегов
name              Edm.String — (read-only, null при записи)
code              Edm.String — (read-only)
```

**PATCH с правильным форматом:**

```python
# ❌ 400 NoDelta
adapter.update_task(task_id, tags=["c98cabfb-...", "e9967692-..."])

# ✅ Работает
adapter.update_task(task_id, tags=[
    {"directoryEntryId": "c98cabfb-...", "directoryId": "d7f2a0a2-..."},
    {"directoryEntryId": "e9967692-...", "directoryId": "d7f2a0a2-..."},
])
```

Метод `TimettaAdapter._format_tags()` выполняет эту конвертацию автоматически: принимает `["uuid"]` или `[{"id": "uuid"}]`, возвращает правильный формат.

---

## 3. Теги нельзя задать при создании задачи

**Проблема.** POST `/Issues` с полем `tags` возвращает 400 «Entity cannot be null», даже если формат правильный.

**Решение:** создавай задачу без тегов, потом патчи отдельно:

```python
# 1. Создать задачу (без tags)
created = adapter.create_task(task_without_tags)
task_id = created["id"]

# 2. Установить теги отдельным PATCH
adapter.update_task(task_id, tags=["tag-uuid-1", "tag-uuid-2"])
```

`submit_task.py` делает это автоматически.

---

## 4. typeId обязателен при создании

**Проблема.** POST `/Issues` без `typeId` возвращает 400 «Entity cannot be null».

```python
# ❌ 400 — typeId отсутствует
{"projectId": "uuid", "name": "Задача"}

# ✅ Работает
{"projectId": "uuid", "name": "Задача", "typeId": "968f71c6-6b38-4845-963a-b2d07ec95185"}
```

Дефолтный `typeId` для стандартных задач: `968f71c6-6b38-4845-963a-b2d07ec95185`.

---

## 5. Спринты — нет projectId, фильтруй по viewId

**Проблема.** Сущность `Sprint` не имеет поля `projectId`. Фильтрация `$filter=projectId eq <uuid>` возвращает 400.

**Решение:** фильтруй по `viewId` — идентификатору доски проекта:

```python
# Найти спринты проекта:
# 1. Взять любую существующую задачу проекта с полем sprintId
# 2. По sprintId найти спринт и его viewId
# 3. Фильтровать все спринты по этому viewId

params = urlencode({
    "$filter": f"viewId eq {VIEW_ID}",
    "$orderby": "startDate desc",
})
sprints = adapter._request("GET", "/Sprints", params=params)
```

---

## 6. isCurrent у спринтов обновляется с задержкой

**Наблюдение.** Флаг `isCurrent` может оставаться `true` у спринта с истёкшими датами и `false` у активного текущего спринта.

**Рекомендация:** не полагайся только на `isCurrent`. Для определения актуального спринта проверяй даты (`startDate`, `endDate`) вместе с флагом.

```python
from datetime import date

def find_current_sprint(sprints):
    today = date.today().isoformat()
    # Предпочитаем спринт с правильными датами
    by_date = [s for s in sprints if s["startDate"] <= today <= s["endDate"]]
    if by_date:
        return by_date[0]
    # Откат на isCurrent
    current = [s for s in sprints if s.get("isCurrent")]
    return current[0] if current else None
```

---

## 7. URL-кодирование $filter обязательно

**Проблема.** Python 3.14+ запрещает пробелы в URL. OData-фильтры вида `$filter=directoryId eq uuid` содержат пробелы и вызывают `InvalidURL`.

**Решение:** используй `urllib.parse.urlencode` для всех параметров запроса:

```python
import urllib.parse

params = urllib.parse.urlencode({
    "$filter": f"(directoryId eq {directory_id})",
    "$select": "id,name",
    "$orderby": "name asc",
})
# → $filter=%28directoryId+eq+uuid%29&$select=id%2Cname&$orderby=name+asc
```

---

## 8. tags не является navigation property — $expand не работает

```http
# ❌ 400 — tags не navigation property
GET /odata/Issues?$expand=tags

# ✅ tags возвращается inline при обычном GET
GET /odata/Issues?$select=id,name,tags
```

---

## 9. PATCH /Issues(uuid)/Comments — может вернуть 404

Некоторые типы задач не поддерживают Comments endpoint. Адаптер обрабатывает это gracefully — возвращает `None` при 404.

---

## Таблица совместимости эндпоинтов

| Операция | Метод | Путь | Статус |
|----------|-------|------|--------|
| Список проектов | GET | `/Projects?$select=id,name,code` | ✅ |
| Список пользователей | GET | `/Users?$select=id,displayName` | ✅ |
| Список тегов | GET | `/DirectoryEntries?$filter=(directoryId eq UUID)` | ✅ |
| Список спринтов | GET | `/Sprints?$filter=viewId eq UUID` | ✅ |
| Создать задачу | POST | `/Issues` (без tags, с typeId) | ✅ |
| Получить задачу | GET | `/Issues(uuid)` | ✅ |
| Обновить задачу | PATCH | `/Issues(uuid)` | ✅ скалярные поля |
| Обновить теги | PATCH | `/Issues(uuid)` (DirectorySetEntry) | ✅ |
| Добавить комментарий | POST | `/Issues(uuid)/Comments` | ⚠️ 404 для некоторых типов |
| Прикрепить файл | POST | `/Issues(uuid)/Attachments` (multipart) | ⚠️ 404 для некоторых типов |
| $expand=tags | GET | — | ❌ 400 |
| POST с tags | POST | `/Issues` | ❌ 400 |

## See Also

- [API-справочник](api-reference.md) — методы адаптера и модель Task
- [Submit Pipeline](submit-pipeline.md) — авто-создание задач из требований
- [OpenAPI Spec](timetta-openapi.yaml) — полная спецификация эндпоинтов
