---
name: timetta-api
description: Use when integrating with Timetta time-tracking API, querying OData endpoints, authenticating with token-api or OAuth, fetching time entries, users, projects, or reporting data from Timetta
---

# Timetta API

## Overview

Timetta exposes two APIs — main OData API and Reporting API. Both require Bearer authentication. No versioning; changes announced 14 days in advance.

## Endpoints

| API | Base URL |
|-----|----------|
| Main OData | `https://api.timetta.com/odata` |
| Reporting | `https://reporting.timetta.com/OData` |
| Auth | `https://auth.timetta.com` |
| OData Metadata | `https://api.timetta.com/odata/$metadata` |

## Authentication

### Token API (статический токен, рекомендуется для автоматизации)

Токен настраивается в разделе настроек Timetta. Передаётся как Bearer:

```http
GET https://api.timetta.com/odata/Users
Authorization: Bearer <TIMETTA_TOKEN>
```

Срок действия: 1 год.

### OAuth 2.0 (Resource Owner Password Grant)

```http
POST https://auth.timetta.com/connect/token
Content-Type: application/x-www-form-urlencoded

client_id=external&grant_type=password&username=EMAIL&password=PASS&scope=all offline_access
```

Ответ содержит `access_token` (TTL 1 час) и `refresh_token` (TTL 15 дней).

**Обновление токена:**
```http
POST https://auth.timetta.com/connect/token
Content-Type: application/x-www-form-urlencoded

client_id=external&grant_type=refresh_token&refresh_token=REFRESH_TOKEN
```

Не храни пароли — храни только refresh_token.

## OData Запросы

Timetta реализует OData v4. Поддерживаются стандартные параметры:

```http
# Выбор полей
GET /odata/Users?$select=id,name,email

# Раскрытие связей
GET /odata/TimeEntries?$expand=Project,User

# Фильтрация
GET /odata/TimeEntries?$filter=Date ge 2024-01-01

# Сортировка и пагинация
GET /odata/Projects?$orderby=Name&$top=50&$skip=0

# Комбинирование
GET /odata/TimeEntries?$filter=UserId eq GUID&$expand=Project&$select=Date,Hours,Comment
```

Метаданные (все сущности и поля): `GET /odata/$metadata`

## Reporting API

```http
GET https://reporting.timetta.com/OData/YOUR_REPORT_DATASOURCE
Authorization: Bearer <TIMETTA_TOKEN>

# Лимит ответа: 500,000 строк
# Для больших датасетов (250k+) используй Query Folding (серверную агрегацию)
```

Поддерживает подключение к Power BI, QlikView, Excel Power Query.

## HTTP коды

| Код | Смысл |
|-----|-------|
| 200–204 | Успех |
| 401 | Не авторизован |
| 403–404 | Нет доступа / не найден |
| 500 | Ошибка бизнес-логики (JSON: `{code, message}`) |

## Пример: получить записи времени за период

```python
import os
import requests

TOKEN = os.environ["TIMETTA_TOKEN"]
BASE = "https://api.timetta.com/odata"

headers = {"Authorization": f"Bearer {TOKEN}"}

params = {
    "$filter": "Date ge 2024-01-01 and Date le 2024-01-31",
    "$expand": "Project,User",
    "$select": "Date,Hours,Comment,Project,User",
}

resp = requests.get(f"{BASE}/TimeEntries", headers=headers, params=params)
resp.raise_for_status()
entries = resp.json()["value"]
```

## Common Mistakes

- **Без `$metadata`** — не знаешь реальные имена полей и сущностей; загрузи метаданные первым делом
- **Хранить пароль** — храни только refresh_token
- **Игнорировать 500** — это бизнес-ошибка с полезным `message`, не системный сбой
- **Большие выборки без фильтров** — Reporting API режет на 500k строк; фильтруй на сервере
