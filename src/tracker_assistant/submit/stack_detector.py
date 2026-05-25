from __future__ import annotations

"""Детектор технологического стека проекта по файловому дереву."""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_FRONTEND_EXTS = frozenset({".tsx", ".jsx", ".vue", ".svelte", ".astro"})
_BACKEND_EXTS = frozenset({".py", ".go", ".java", ".rb", ".rs", ".cs", ".php"})
_SKIP_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "coverage",
})

_FILE_MARKERS: dict[str, tuple[str, str]] = {
    "next.config.js":   ("Next.js",   "frontend"),
    "next.config.ts":   ("Next.js",   "frontend"),
    "nuxt.config.ts":   ("Nuxt.js",   "frontend"),
    "vite.config.ts":   ("Vite",      "frontend"),
    "vite.config.js":   ("Vite",      "frontend"),
    "angular.json":     ("Angular",   "frontend"),
    "svelte.config.js": ("SvelteKit", "frontend"),
    "pyproject.toml":   ("Python",    "backend"),
    "requirements.txt": ("Python",    "backend"),
    "go.mod":           ("Go",        "backend"),
    "Cargo.toml":       ("Rust",      "backend"),
    "pom.xml":          ("Java",      "backend"),
    "Gemfile":          ("Ruby",      "backend"),
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

    for filename, (tech, layer) in _FILE_MARKERS.items():
        if (project_path / filename).exists():
            if tech not in technologies:
                technologies.append(tech)
            layers.add(layer)

    for hint, layer in _DIR_HINTS.items():
        if (project_path / hint).is_dir():
            layers.add(layer)

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

    description = ""
    for readme in ("README.md", "README.rst", "README.txt"):
        p = project_path / readme
        if p.exists():
            description = p.read_text(encoding="utf-8", errors="replace")[:800]
            break

    logger.debug(
        "stack scan: layers=%s techs=%s fe=%d be=%d total=%d",
        layers, technologies, frontend_count, backend_count, file_total,
    )
    return {
        "has_frontend": "frontend" in layers,
        "has_backend":  "backend"  in layers,
        "technologies": technologies,
        "description":  description,
    }


def build_stack_context(stack: dict[str, Any]) -> str:
    """Сформировать текстовый блок описания стека для промпта."""
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


def empty_stack() -> dict[str, Any]:
    return {"has_frontend": False, "has_backend": False, "technologies": [], "description": ""}
