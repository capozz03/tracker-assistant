from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..models import Task
from .timetta_auth import TimettaAuth

logger = logging.getLogger(__name__)


class TimettaAdapter:
    BASE = "https://api.timetta.com/odata"

    def __init__(self, token: str = "", auth: TimettaAuth | None = None) -> None:
        self._token = token
        self._auth = auth

    def _get_token(self, *, force_refresh: bool = False) -> str:
        if self._auth is not None:
            return self._auth.get_token(force_refresh=force_refresh)
        return self._token

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        params: str = "",
        *,
        _retried: bool = False,
    ) -> Any:
        url = f"{self.BASE}{path}"
        if params:
            url = f"{url}?{params}"
        headers = {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        }
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        logger.debug("→ %s %s body=%s", method, path, body)
        req = urllib.request.Request(url=url, method=method, headers=headers, data=data)
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8").strip()
                result = json.loads(raw) if raw else {}
                logger.debug("← %s %s status=200", method, path)
                return result
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and self._auth is not None and not _retried:
                logger.info("[FIX] token: 401 on %s %s — refreshing token and retrying", method, path)
                self._auth.get_token(force_refresh=True)
                return self._request(method, path, body, params, _retried=True)
            payload = exc.read().decode("utf-8", errors="replace")
            logger.error("← %s %s status=%d body=%s", method, path, exc.code, payload)
            raise RuntimeError(f"Timetta {method} {path} → {exc.code}: {payload}") from exc

    def get_projects(self) -> list[dict[str, Any]]:
        logger.debug("Fetching projects")
        result = self._request("GET", "/Projects", params="$select=id,name,code")
        items: list[dict[str, Any]] = result.get("value", result) if isinstance(result, dict) else result
        logger.debug("Got %d projects", len(items))
        return items

    def get_users(self) -> list[dict[str, Any]]:
        logger.debug("Fetching users")
        result = self._request("GET", "/Users", params="$select=id,displayName")
        items: list[dict[str, Any]] = result.get("value", result) if isinstance(result, dict) else result
        logger.debug("Got %d users", len(items))
        return items

    def get_tags(self) -> list[dict[str, Any]]:
        logger.debug("Fetching tags")
        try:
            result = self._request("GET", "/Tags", params="$select=id,name")
        except RuntimeError as exc:
            if "404" in str(exc):
                logger.warning("Tags not supported by this Timetta instance — returning empty list")
                return []
            raise
        items: list[dict[str, Any]] = result.get("value", result) if isinstance(result, dict) else result
        logger.debug("Got %d tags", len(items))
        return items

    def create_task(self, task: Task) -> dict[str, Any]:
        body = task.to_api_body()
        logger.debug("[FIX] Creating task via /Issues: project=%s name=%r", task.project_id, task.summary)
        result = self._request("POST", "/Issues", body)
        logger.debug("[FIX] Created task id=%s", result.get("id"))
        return result

    def get_task(self, task_id: str) -> dict[str, Any]:
        logger.debug("Getting task %s", task_id)
        return self._request("GET", f"/Issues('{task_id}')")

    def update_task(self, task_id: str, **fields: Any) -> dict[str, Any]:
        logger.debug("Updating task %s fields=%s", task_id, list(fields.keys()))
        return self._request("PATCH", f"/Issues('{task_id}')", fields)

    def add_comment(self, task_id: str, text: str) -> dict[str, Any] | None:
        logger.debug("Adding comment to task %s (len=%d)", task_id, len(text))
        try:
            return self._request(
                "POST",
                f"/Issues('{task_id}')/Comments",
                {"text": text},
            )
        except RuntimeError as exc:
            if "404" in str(exc):
                logger.warning("Comments not supported for Issues — skipping (task=%s)", task_id)
                return None
            raise

    def attach_file(self, task_id: str, filepath: str) -> dict[str, Any] | None:
        path = Path(filepath)
        logger.debug("Attaching file %s to task %s", path.name, task_id)
        url = f"{self.BASE}/Issues('{task_id}')/Attachments"
        with path.open("rb") as fh:
            content = fh.read()
        boundary = "----TimettaBoundary"
        multipart = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()

        def _do_attach(*, force_refresh: bool = False) -> dict[str, Any] | None:
            headers = {
                "Authorization": f"Bearer {self._get_token(force_refresh=force_refresh)}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            }
            req = urllib.request.Request(url=url, method="POST", headers=headers, data=multipart)
            try:
                with urllib.request.urlopen(req) as resp:
                    raw = resp.read().decode("utf-8").strip()
                    result: dict[str, Any] = json.loads(raw) if raw else {}
                    logger.debug("Attached file %s to task %s", path.name, task_id)
                    return result
            except urllib.error.HTTPError as exc:
                if exc.code == 401 and self._auth is not None and not force_refresh:
                    logger.info("[FIX] token: 401 on attach_file — refreshing token and retrying")
                    return _do_attach(force_refresh=True)
                payload = exc.read().decode("utf-8", errors="replace")
                if exc.code == 404:
                    logger.warning("Attachments not supported for Issues — skipping (task=%s)", task_id)
                    return None
                logger.error("attach_file failed: %d %s", exc.code, payload)
                raise RuntimeError(f"attach_file {task_id} → {exc.code}: {payload}") from exc

        return _do_attach()
