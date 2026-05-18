from __future__ import annotations

import json
import os
from pathlib import Path


def load_env(root: Path) -> dict[str, str]:
    """Read KEY=VALUE pairs from .env in root, falling back to environment variables."""
    env_path = root / ".env"
    values: dict[str, str] = {}
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    # environment variables take precedence over .env
    for key in list(values):
        if key in os.environ:
            values[key] = os.environ[key]
    return values


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
