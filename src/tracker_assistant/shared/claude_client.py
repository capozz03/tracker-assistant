from __future__ import annotations

"""Общий клиент для вызова claude -p.

Используется в tracker_assistant.submit и tracker_assistant.enrich.
Единственное место, где живёт логика извлечения JSON из ответа claude -p.
"""

import json
import logging
import re
import subprocess
import tempfile
from typing import Any

logger = logging.getLogger(__name__)


def call_claude(prompt: str) -> Any:
    """Вызвать claude -p и вернуть распарсенный JSON (dict или list).

    Извлекает JSON из ответа: сначала ищет ```json ... ``` fence,
    затем находит первый символ [ или {.
    Промпт передаётся через stdin, чтобы избежать ограничений ARG_MAX.
    Запускается в нейтральной директории: иначе claude подхватил бы
    CLAUDE.md проекта и его ограничения попали бы в генерацию задач.
    Флаг --bare НЕ используется: он читает только ANTHROPIC_API_KEY и
    игнорирует OAuth/keychain (подписочный логин), что ломает вызов.
    """
    logger.debug("call_claude: prompt=%d chars", len(prompt))
    with tempfile.TemporaryDirectory() as neutral_cwd:
        result = subprocess.run(
            ["claude", "-p", "--dangerously-skip-permissions"],
            input=prompt,
            capture_output=True,
            text=True,
            check=False,
            cwd=neutral_cwd,
        )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "(нет вывода)"
        logger.error(
            "call_claude: код=%d stderr=%r stdout=%r",
            result.returncode, result.stderr[:500], result.stdout[:500],
        )
        raise RuntimeError(
            f"claude -p завершился с ошибкой (код {result.returncode}):\n{detail}"
        )
    output = result.stdout.strip()
    logger.debug("call_claude: received %d chars", len(output))

    # Вытащить JSON: код-блок или первый [...] / {...}
    fence = re.search(r"```(?:json)?\s*\n(.*?)\n```", output, re.DOTALL)
    if fence:
        output = fence.group(1).strip()
    else:
        m = re.search(r"[\[\{]", output)
        if m:
            output = output[m.start():]

    try:
        parsed = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"claude -p вернул невалидный JSON: {exc}\n"
            f"Вывод (первые 400 символов): {output[:400]}"
        )
    logger.debug("call_claude: parsed type=%s", type(parsed).__name__)
    return parsed


def call_claude_list(prompt: str) -> list[dict[str, Any]]:
    """Вызвать claude -p и вернуть список task-dict'ов.

    Если Claude вернул одиночный dict — оборачивает в список.
    Используется в submit.service.
    """
    parsed = call_claude(prompt)
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        raise RuntimeError(f"ожидался JSON-массив, получено {type(parsed).__name__}")
    return parsed


def call_claude_dict(prompt: str) -> dict[str, Any]:
    """Вызвать claude -p и вернуть одиночный dict.

    Используется в enrich.service.
    """
    parsed = call_claude(prompt)
    if isinstance(parsed, list) and len(parsed) == 1:
        return parsed[0]
    if not isinstance(parsed, dict):
        raise RuntimeError(
            f"ожидался JSON-объект, получено {type(parsed).__name__}"
        )
    return parsed
