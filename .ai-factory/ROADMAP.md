# Project Roadmap

> Минималистичный Python-клиент и Telegram-бот для автоматизации управления задачами Timetta через LLM

## Milestones

- [x] **Timetta API client** — TimettaAdapter с полным CRUD: задачи, теги, пользователи, проекты, комментарии, вложения
- [x] **Task creation pipeline** — LLM-driven пайплайн: анализ стека → промпт → submit_requirements через Claude
- [x] **Task enrichment via LLM** — enrich_task: форматирует сырые требования, подбирает теги и исполнителя
- [x] **CLI toolset** — 4 entry point: task-cli, task-submit, task-enrich, task-telegram
- [x] **Telegram bot foundation** — config, project registry, bot factory, базовые хендлеры
- [x] **Telegram: media & forwarded messages** — поддержка фото с подписью, документов, пересланных сообщений
- [x] **Telegram: VPS codebase sync** — rsync/git clone перед submit для анализа стека удалённого проекта
- [x] **Telegram: interactive project selection & favourites** — /project из Timetta API с inline-кнопками, /favorites
- [x] **Docker deployment** — Dockerfile, compose.yml, compose.override.yml, compose.production.yml
- [x] **Centralized logging** — shared/logging.py, настройка через LOG_LEVEL env var
- [ ] **Fix: tag assignment in task creation** — задача создаётся с пустым тегом вместо "backend" / "frontend"; диагностика и фикс логики выбора тега в LLM-пайплайне (enrich_task или submit_requirements)
- [ ] **Persistent bot state** — PicklePersistence или SQLite: избранные и активный проект выживают рестарт
- [ ] **Telegram: pinned active project message** — при выборе проекта в чате закрепляется сообщение с его именем; визуально показывает активный контекст без необходимости помнить, в каком проекте работаешь
- [ ] **Telegram: loading indicators & progress feedback** — анимация во время долгих операций: send_chat_action("typing"), прогресс-сообщение с редактируемыми точками ("Создаю задачу · / ··· / ···"); пользователь видит, что бот работает, а не завис
- [ ] **Task query & search via bot** — /tasks команда: поиск и просмотр задач проекта через inline-кнопки
- [ ] **Sprint management via bot** — /sprint: список спринтов, выбор активного, привязка к задачам
- [ ] **Time entries via bot** — /log: логирование времени; /time: просмотр записей за период
- [ ] **Webhook production mode** — замена polling на webhook (SSL + reverse proxy) для продакшн-деплоя
- [ ] **Reporting & analytics** — /report: недельная сводка по задачам и времени в чат

## Completed

| Milestone | Date |
|-----------|------|
| Timetta API client | 2026-05-25 |
| Task creation pipeline | 2026-05-25 |
| Task enrichment via LLM | 2026-05-25 |
| CLI toolset | 2026-05-25 |
| Telegram bot foundation | 2026-05-25 |
| Telegram: media & forwarded messages | 2026-05-25 |
| Telegram: VPS codebase sync | 2026-05-25 |
| Telegram: interactive project selection & favourites | 2026-05-25 |
| Docker deployment | 2026-05-25 |
| Centralized logging | 2026-05-25 |
