# Подготовка к продакшену: Docker + логирование по окружению

**Создан:** 2026-05-25  
**Режим:** fast

## Настройки

- **Тестирование:** да
- **Логирование:** verbose (DEBUG) в dev, WARNING в prod
- **Docs:** нет

## Задачи

<!-- parallel: tasks 1, 2, 4 -->
- [x] 1. **`/aif-dockerize`** — сгенерировать Docker-конфигурацию
  - Запустить скилл `/aif-dockerize` для генерации:
    - `Dockerfile` (multi-stage: `dev` + `prod`)
    - `compose.yml` — базовая конфигурация сервиса
    - `compose.override.yml` — дев-оверрайд: `LOG_LEVEL=DEBUG`, маунт исходников
    - `compose.production.yml` — прод-конфиг: `LOG_LEVEL=WARNING`, no-mounts, restart policy
    - `.dockerignore` — исключить `.env`, `cache/`, `__pycache__`, `.ai-factory/`, тесты
  - Проверить что entry point указывает на `task-cli` (установленный через `pip install -e .`)
  - Лог: в Dockerfile добавить `ENV LOG_LEVEL=WARNING` как дефолт

- [x] 2. **`shared/logging.py`** — централизованная настройка логирования
  - Создать `src/tracker_assistant/shared/logging.py`:
    ```python
    def configure_logging(cli_level: str | None = None) -> None:
        """Настроить логирование: CLI-флаг > LOG_LEVEL env > WARNING (prod default)."""
    ```
  - Приоритет: `cli_level` (из `--log-level`) → `os.environ.get("LOG_LEVEL")` → `"WARNING"`
  - `basicConfig(level=..., format="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%H:%M:%S")`
  - Лог: `logging.debug("logging configured: level=%s (source=%s)", level, source)`
  - Файл: `src/tracker_assistant/shared/logging.py`

<!-- parallel: tasks 3, 5 -->
- [x] 3. **Обновить все CLI** — использовать `configure_logging` вместо дублирующегося `basicConfig`
  - `timetta/cli.py`: убрать `_setup_logging()`, заменить вызов на `configure_logging(args.log_level)`
  - `submit/cli.py`: убрать inline `logging.basicConfig(...)`, вызвать `configure_logging(args.log_level)`
  - `enrich/cli.py`: то же самое
  - Дефолт `--log-level` в argparse оставить `None` (чтобы `configure_logging` знал «не передано»)
  - Файлы: `src/tracker_assistant/timetta/cli.py`, `src/tracker_assistant/submit/cli.py`, `src/tracker_assistant/enrich/cli.py`

- [x] 4. **Обновить `.env.example`** — добавить `LOG_LEVEL=DEBUG` с комментарием
  ```env
  # Уровень логирования: DEBUG (dev) | INFO | WARNING (prod default)
  # В Docker-прод контейнере LOG_LEVEL=WARNING задаётся через compose.production.yml
  LOG_LEVEL=DEBUG
  ```
  - Файл: `.env.example`

- [x] 5. **Тесты** — `tests/test_logging.py`
  - `test_cli_level_overrides_env` — передан `cli_level="INFO"`, `LOG_LEVEL=DEBUG` → уровень INFO
  - `test_env_level_used_when_no_cli` — `cli_level=None`, `LOG_LEVEL=DEBUG` → уровень DEBUG
  - `test_default_warning_when_nothing_set` — `cli_level=None`, нет `LOG_LEVEL` в env → уровень WARNING
  - `test_invalid_level_falls_back_to_warning` — `LOG_LEVEL=BADLEVEL` → уровень WARNING + лог предупреждения
  - Файл: `tests/test_logging.py`

## Commit Plan

| После задачи | Коммит |
|---|---|
| 1 | `chore(docker): add Dockerfile and compose configs` |
| 4 | `feat(logging): centralize log-level config via LOG_LEVEL env var` |
| 5 | `test(logging): add tests for configure_logging` |
