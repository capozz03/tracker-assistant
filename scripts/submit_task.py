from __future__ import annotations

"""submit_task.py — полный пайплайн: требования → анализ стека → задачи в Timetta.

Использование:
    uv run python scripts/submit_task.py \\
        --requirements "Улучшить поиск: кнопка Найти, сохранять запрос при смене вкладки" \\
        --project-path /path/to/tourist-app \\
        --project-id <timetta-project-uuid>

    # Из файла требований
    uv run python scripts/submit_task.py \\
        --requirements-file tasks.md \\
        --project-path /path/to/tourist-app

    # TIMETTA_PROJECT_ID можно прописать в .env вместо --project-id
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tracker_assistant.adapters.timetta_adapter import TimettaAdapter
from tracker_assistant.io_utils import load_cached, load_env
from tracker_assistant.models import Task
from tracker_assistant.pipeline import create_task

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stack detection
# ---------------------------------------------------------------------------

_FRONTEND_EXTS = frozenset({".tsx", ".jsx", ".vue", ".svelte", ".astro"})
_BACKEND_EXTS = frozenset({".py", ".go", ".java", ".rb", ".rs", ".cs", ".php"})
_SKIP_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "coverage",
})

_FILE_MARKERS: dict[str, tuple[str, str]] = {
    # filename → (technology, layer)
    "next.config.js":   ("Next.js",  "frontend"),
    "next.config.ts":   ("Next.js",  "frontend"),
    "nuxt.config.ts":   ("Nuxt.js",  "frontend"),
    "vite.config.ts":   ("Vite",     "frontend"),
    "vite.config.js":   ("Vite",     "frontend"),
    "angular.json":     ("Angular",  "frontend"),
    "svelte.config.js": ("SvelteKit","frontend"),
    "pyproject.toml":   ("Python",   "backend"),
    "requirements.txt": ("Python",   "backend"),
    "go.mod":           ("Go",       "backend"),
    "Cargo.toml":       ("Rust",     "backend"),
    "pom.xml":          ("Java",     "backend"),
    "Gemfile":          ("Ruby",     "backend"),
}

_NPM_LIBS: dict[str, tuple[str, str]] = {
    "react":          ("React",   "frontend"),
    "vue":            ("Vue.js",  "frontend"),
    "@angular/core":  ("Angular", "frontend"),
    "svelte":         ("Svelte",  "frontend"),
    "next":           ("Next.js", "frontend"),
    "nuxt":           ("Nuxt.js", "frontend"),
    "express":        ("Express", "backend"),
    "fastify":        ("Fastify", "backend"),
    "@nestjs/core":   ("NestJS",  "backend"),
}

_DIR_HINTS: dict[str, str] = {
    "frontend": "frontend", "web": "frontend", "client": "frontend",
    "app": "frontend",      "mobile": "frontend",
    "backend": "backend",   "api": "backend",  "server": "backend",
    "services": "backend",
}


def scan_project_stack(project_path: Path) -> dict[str, Any]:
    """Лёгкий анализ стека по файловому дереву (глубина ≤ 3, макс 500 файлов)."""
    if not project_path.exists():
        logger.warning("project_path не существует: %s", project_path)
        return {"has_frontend": False, "has_backend": False,
                "technologies": [], "description": ""}

    technologies: list[str] = []
    layers: set[str] = set()

    # 1. Маркерные файлы в корне
    for filename, (tech, layer) in _FILE_MARKERS.items():
        if (project_path / filename).exists():
            if tech not in technologies:
                technologies.append(tech)
            layers.add(layer)

    # 2. Директории-подсказки (глубина 1)
    for hint, layer in _DIR_HINTS.items():
        if (project_path / hint).is_dir():
            layers.add(layer)

    # 3. package.json зависимости
    pkg_path = project_path / "package.json"
    if pkg_path.exists():
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
            all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            for lib, (label, layer) in _NPM_LIBS.items():
                if lib in all_deps:
                    if label not in technologies:
                        technologies.append(label)
                    layers.add(layer)
        except Exception as exc:
            logger.debug("package.json: %s", exc)

    # 4. Подсчёт расширений (глубина ≤ 3, лимит 500 файлов)
    frontend_count = backend_count = file_total = 0

    def _walk(path: Path, depth: int) -> None:
        nonlocal frontend_count, backend_count, file_total
        if depth > 3 or file_total >= 500:
            return
        try:
            for entry in path.iterdir():
                if file_total >= 500:
                    break
                if entry.is_dir() and entry.name not in _SKIP_DIRS:
                    _walk(entry, depth + 1)
                elif entry.is_file():
                    file_total += 1
                    if entry.suffix in _FRONTEND_EXTS:
                        frontend_count += 1
                    elif entry.suffix in _BACKEND_EXTS:
                        backend_count += 1
        except PermissionError:
            pass

    _walk(project_path, 0)

    if frontend_count > 0:
        layers.add("frontend")
    if backend_count > 0:
        layers.add("backend")

    # 5. README (первые 800 символов)
    description = ""
    for readme in ("README.md", "README.rst", "README.txt"):
        p = project_path / readme
        if p.exists():
            description = p.read_text(encoding="utf-8", errors="replace")[:800]
            break

    logger.debug(
        "stack scan: layers=%s techs=%s fe_files=%d be_files=%d total=%d",
        layers, technologies, frontend_count, backend_count, file_total,
    )
    return {
        "has_frontend": "frontend" in layers,
        "has_backend":  "backend"  in layers,
        "technologies": technologies,
        "description":  description,
    }


def _build_stack_context(stack: dict[str, Any]) -> str:
    parts: list[str] = []
    if stack["description"]:
        parts.append(f"**Описание проекта:**\n{stack['description']}")
    if stack["technologies"]:
        parts.append(f"**Технологии:** {', '.join(stack['technologies'])}")
    layers = []
    if stack["has_frontend"]:
        layers.append("фронтенд")
    if stack["has_backend"]:
        layers.append("бэкенд")
    parts.append(f"**Слои:** {', '.join(layers) if layers else 'не определено'}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Claude call
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
Ты — ассистент по управлению задачами для команды разработчиков.

## Стек проекта
{stack_context}

## Доступные теги (используй только эти UUID)
{tags}

## Доступные исполнители (используй только эти UUID)
{users}

## Требования
{requirements}

---

## Правила создания задач

**Разбивка по слоям:**
- Если задача затрагивает И фронтенд, И бэкенд — создай ДВЕ задачи:
  "Frontend: <суть>" с тегом фронтенда и "Backend: <суть>" с тегом бэкенда.
- Если задача только одного слоя — одна задача.
- Если задача организационная (аналитика, документация) — одна задача.

**Каждая задача содержит:**
- `summary`: "[Слой]: <суть>" — например "Frontend: UI полнотекстового поиска"
- `description`: Markdown — контекст, что конкретно сделать, критерии приёмки
- `tags`: массив из 1-2 UUID из списка выше (слой + тематический при наличии)
- `assignee`: UUID исполнителя если имя явно подходит, иначе ""
- `project_id`: "{project_id}" — не менять

**Не выдумывай UUID.** Используй только те, что в списках выше.

Верни ТОЛЬКО валидный JSON-массив без markdown-обёртки и пояснений:
[
  {{
    "project_id": "{project_id}",
    "summary": "...",
    "description": "...",
    "tags": ["uuid"],
    "assignee": "",
    "comments": [],
    "attachments": []
  }}
]
"""


def _call_claude(prompt: str) -> list[dict[str, Any]]:
    logger.debug("_call_claude: prompt=%d chars", len(prompt))
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"ERROR: claude -p завершился с ошибкой (код {result.returncode}):\n"
            f"{result.stderr.strip()}"
        )
    output = result.stdout.strip()
    logger.debug("_call_claude: received %d chars", len(output))

    # Вытащить JSON из ответа: код-блок или первый [...] / {...}
    import re as _re
    fence = _re.search(r"```(?:json)?\s*\n(.*?)\n```", output, _re.DOTALL)
    if fence:
        output = fence.group(1).strip()
    else:
        m = _re.search(r"[\[\{]", output)
        if m:
            output = output[m.start():]

    try:
        parsed = json.loads(output)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"ERROR: claude -p вернул невалидный JSON: {exc}\n"
            f"Вывод (первые 400 символов): {output[:400]}"
        )

    # Claude иногда возвращает объект вместо массива
    if isinstance(parsed, dict):
        parsed = [parsed]

    if not isinstance(parsed, list):
        raise SystemExit(f"ERROR: ожидался JSON-массив, получено {type(parsed).__name__}")

    return parsed


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def _build_adapter(root: Path) -> TimettaAdapter:
    env = load_env(root)
    token = env.get("TIMETTA_TOKEN") or os.environ.get("TIMETTA_TOKEN", "")
    if not token:
        raise SystemExit("ERROR: TIMETTA_TOKEN не задан (добавь в .env)")
    tags_dir_id = (
        env.get("TIMETTA_TAGS_DIR_ID")
        or os.environ.get("TIMETTA_TAGS_DIR_ID", "")
        or TimettaAdapter.DEFAULT_TAGS_DIR_ID
    )
    return TimettaAdapter(token=token, tags_dir_id=tags_dir_id)


def submit_requirements(
    requirements: str,
    project_id: str,
    adapter: TimettaAdapter,
    users: list[dict[str, Any]],
    tags: list[dict[str, Any]],
    project_path: Path | None,
    root: Path,
    sprint_id: str = "",
    default_task_type: str = "968f71c6-6b38-4845-963a-b2d07ec95185",
) -> list[dict[str, Any]]:
    """Полный пайплайн: requirements → stack → claude → create задачи в Timetta."""

    # 1. Анализ стека
    if project_path:
        stack = scan_project_stack(project_path)
    else:
        logger.info("--project-path не указан, стек не определяется")
        stack = {"has_frontend": False, "has_backend": False,
                 "technologies": [], "description": ""}

    stack_context = _build_stack_context(stack)

    # 2. Формируем промпт
    tags_text = "\n".join(
        f"  - id={t.get('id', '')} name={t.get('name', '')}" for t in tags
    ) or "  (теги не найдены)"

    users_text = "\n".join(
        f"  - id={u.get('id', '')} name={u.get('displayName', '')}" for u in users
    ) or "  (исполнители не найдены)"

    prompt = _PROMPT_TEMPLATE.format(
        stack_context=stack_context,
        tags=tags_text,
        users=users_text,
        requirements=requirements,
        project_id=project_id,
    )

    # 3. Обогащение через Claude
    task_dicts = _call_claude(prompt)
    logger.info("Claude вернул %d задач(и)", len(task_dicts))

    # 4. Создаём каждую задачу
    results: list[dict[str, Any]] = []
    for idx, task_dict in enumerate(task_dicts, 1):
        task_dict.setdefault("project_id", project_id)
        # typeId обязателен для Timetta — используем дефолтный тип если Claude не указал
        if not task_dict.get("task_type"):
            task_dict["task_type"] = default_task_type
        if sprint_id:
            task_dict.setdefault("extra", {})["sprintId"] = sprint_id

        # Tags идут отдельным PATCH после создания — POST /Issues не принимает строки-UUID
        pending_tags = task_dict.pop("tags", [])
        pending_assignee = task_dict.get("assignee", "")

        task = Task.from_dict(task_dict)
        logger.info("[%d/%d] Создаю: %r", idx, len(task_dicts), task.summary)

        created = create_task(adapter, task, root=root)
        task_id = created.get("id", "")

        # Обновляем теги и исполнителя отдельным вызовом
        if task_id and (pending_tags or pending_assignee):
            update_fields: dict[str, Any] = {}
            if pending_tags:
                update_fields["tags"] = pending_tags
            if pending_assignee:
                update_fields["assigneeId"] = pending_assignee
            logger.debug("[%d/%d] update tags=%s assignee=%s", idx, len(task_dicts), pending_tags, pending_assignee)
            adapter.update_task(task_id, **update_fields)

        results.append({
            "id":       task_id,
            "summary":  task.summary,
            "tags":     pending_tags,
            "assignee": pending_assignee,
            "url":      f"https://app.timetta.com/issues/{task_id}" if task_id else "",
        })
        logger.info("[%d/%d] Создана id=%s", idx, len(task_dicts), task_id)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Создать задачи в Timetta из текстовых требований",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--root", default=".",
                        help="Путь к корню tracker-assistant (содержит .env)")
    parser.add_argument("--requirements",
                        help="Текст требований напрямую")
    parser.add_argument("--requirements-file",
                        help="Путь к файлу с требованиями (.md/.txt)")
    parser.add_argument("--project-id",
                        help="UUID проекта в Timetta (или TIMETTA_PROJECT_ID в .env)")
    parser.add_argument("--project-path",
                        help="Путь к анализируемой кодовой базе (необязательно)")
    parser.add_argument("--sprint-id",
                        help="UUID спринта в Timetta (необязательно)")
    parser.add_argument("--no-cache", action="store_true",
                        help="Игнорировать кеш пользователей/тегов")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )

    root = Path(args.root).resolve()

    # --- Требования ---
    if args.requirements:
        requirements = args.requirements
    elif args.requirements_file:
        req_path = Path(args.requirements_file)
        if not req_path.is_absolute():
            req_path = root / req_path
        if not req_path.exists():
            raise SystemExit(f"ERROR: файл не найден: {req_path}")
        requirements = req_path.read_text(encoding="utf-8")
        logger.info("Требования загружены из %s (%d символов)", req_path, len(requirements))
    elif not sys.stdin.isatty():
        requirements = sys.stdin.read().strip()
        if not requirements:
            raise SystemExit("ERROR: пустой stdin")
    else:
        raise SystemExit(
            "ERROR: укажи --requirements \"текст\" или --requirements-file path.md"
        )

    # --- Project ID ---
    env = load_env(root)
    project_id = (
        args.project_id
        or env.get("TIMETTA_PROJECT_ID")
        or os.environ.get("TIMETTA_PROJECT_ID", "")
    )
    if not project_id:
        raise SystemExit(
            "ERROR: укажи --project-id <uuid> или добавь TIMETTA_PROJECT_ID в .env"
        )

    # --- Project path ---
    project_path = Path(args.project_path).resolve() if args.project_path else None

    # --- Адаптер + кеши ---
    adapter = _build_adapter(root)
    users = load_cached(root, "users", adapter.get_users, no_cache=args.no_cache)
    tags  = load_cached(root, "tags",  adapter.get_tags,  no_cache=args.no_cache)
    logger.debug("Загружено: %d тегов, %d исполнителей", len(tags), len(users))

    # --- Пайплайн ---
    results = submit_requirements(
        requirements=requirements,
        project_id=project_id,
        adapter=adapter,
        users=users,
        tags=tags,
        project_path=project_path,
        root=root,
        sprint_id=args.sprint_id or "",
    )

    # --- Вывод ---
    print(json.dumps(results, ensure_ascii=False, indent=2))

    print(f"\n✅ Создано задач: {len(results)}", file=sys.stderr)
    for r in results:
        print(f"  • {r['summary']}", file=sys.stderr)
        if r.get("url"):
            print(f"    {r['url']}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
