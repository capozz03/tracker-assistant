from __future__ import annotations

"""Общий клиент для вызова claude -p.

Используется в tracker_assistant.submit и tracker_assistant.enrich.
Единственное место, где живёт логика извлечения JSON из ответа claude -p.
"""

import json
import logging
import re
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


def call_claude(prompt: str) -> Any:
    """Вызвать claude -p и вернуть распарсенный JSON (dict или list).

    Извлекает JSON из ответа: сначала ищет ```json ... ``` fence,
    затем находит первый символ [ или {.
    """
    logger.debug("call_claude: prompt=%d chars", len(prompt))
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
        raise SystemExit(
            f"ERROR: claude -p вернул невалидный JSON: {exc}\n"
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
        raise SystemExit(f"ERROR: ожидался JSON-массив, получено {type(parsed).__name__}")
    return parsed


def call_claude_dict(prompt: str) -> dict[str, Any]:
    """Вызвать claude -p и вернуть одиночный dict.

    Используется в enrich.service.
    """
    parsed = call_claude(prompt)
    if isinstance(parsed, list) and len(parsed) == 1:
        return parsed[0]
    if not isinstance(parsed, dict):
        raise SystemExit(
            f"ERROR: ожидался JSON-объект, получено {type(parsed).__name__}"
        )
    return parsed
