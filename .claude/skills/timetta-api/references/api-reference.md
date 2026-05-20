# Timetta OData v4 API — справочник

## Базовый URL

```
https://api.timetta.com/odata
```

## Аутентификация

```
Authorization: Bearer <TIMETTA_TOKEN>
Content-Type: application/json
```

## Основные эндпоинты

| Ресурс | Метод | URL |
|---|---|---|
| Проекты | GET | `/Projects` |
| Задачи | GET | `/WorkItems` |
| Создать задачу | POST | `/WorkItems` |
| Обновить задачу | PATCH | `/WorkItems('{id}')` |
| Получить задачу | GET | `/WorkItems('{id}')` |
| Добавить комментарий | POST | `/WorkItems('{id}')/Comments` |
| Прикрепить файл | POST | `/WorkItems('{id}')/Attachments` |
| Пользователи | GET | `/Users` |
| Теги | GET | `/Tags` |

## Создание задачи (POST /WorkItems)

```json
{
  "projectId": "uuid",
  "name": "Название задачи",
  "description": "Описание",
  "typeId": "uuid",
  "assigneeId": "user-uuid",
  "tags": ["tag-uuid1", "tag-uuid2"]
}
```

Ответ содержит `id` созданной задачи.

## Обновление задачи (PATCH /WorkItems('{id}'))

```json
{
  "assigneeId": "user-uuid",
  "tags": ["tag-uuid1"]
}
```

## Комментарий (POST /WorkItems('{id}')/Comments)

```json
{
  "text": "Текст комментария"
}
```

## Вложение (POST /WorkItems('{id}')/Attachments)

Multipart form-data с полем `file`.

## OData-фильтрация

```
/WorkItems?$filter=projectId eq 'uuid'
/WorkItems?$select=id,name,status
/WorkItems?$top=100&$skip=0
/WorkItems?$expand=assignee,tags
```

## UUID-поля

Все ID в Timetta — UUID v4 (формат: `xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx`).
Теги и типы задач тоже идентифицируются UUID, а не строками.
