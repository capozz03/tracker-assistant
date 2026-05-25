# Миграция на Structured Modules

**Цель:** Переструктурировать `src/tracker_assistant/` на три независимых модуля (`timetta`, `submit`, `enrich`) + `shared/`. Скрипты становятся тонкими CLI-обёртками.

**Контекст:** см. `.ai-factory/ARCHITECTURE.md` → раздел «Миграция из текущего состояния»

Docs: no
Tests: yes

## Задачи

- [x] 1. Создать `shared/` — io_utils + claude_client (дедупликация _call_claude)
- [x] 2. Создать `timetta/` — models, adapter, service
- [x] 3. Создать `submit/` — stack_detector, prompt, service
- [x] 4. Создать `enrich/` — service (использует shared.claude_client)
- [x] 5. Обновить `src/tracker_assistant/__init__.py` — re-export из новых путей
- [x] 6. Облегчить скрипты — task_cli, submit_task, enrich_task → тонкие обёртки
- [x] 7. Обновить тесты — исправить импорты, добавить тесты для новых модулей
- [x] 8. Удалить legacy-файлы — models.py, pipeline.py, io_utils.py, adapters/
- [x] 9. Финальная проверка — pytest, lint, ручной smoke-test

## Примечание

Backward compat: `from tracker_assistant import Task, TimettaAdapter` должен работать
после миграции через re-exports в `__init__.py`.
