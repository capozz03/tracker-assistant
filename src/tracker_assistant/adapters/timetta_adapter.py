from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..models import Task

logger = logging.getLogger(__name__)


class TimettaAdapter:
    BASE = "https://api.timetta.com/odata"
    # Timetta stores tags as DirectoryEntries under a fixed system directory.
    # Override with TIMETTA_TAGS_DIR_ID env var if your instance differs.
    DEFAULT_TAGS_DIR_ID = "d7f2a0a2-c449-488e-9738-044cb99ff173"

    def __init__(self, token: str = "", *, tags_dir_id: str = DEFAULT_TAGS_DIR_ID) -> None:
        self._token = token
        self._tags_dir_id = tags_dir_id

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        params: str = "",
        *,
        quiet: bool = False,
    ) -> Any:
        url = f"{self.BASE}{path}"
        if params:
            url = f"{url}?{params}"
        headers = {
            "Authorization": f"Bearer {self._token}",
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
            payload = exc.read().decode("utf-8", errors="replace")
            log_fn = logger.debug if quiet else logger.error
            log_fn("← %s %s status=%d body=%s", method, path, exc.code, payload)
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
        logger.debug("Fetching tags from DirectoryEntries (dir=%s)", self._tags_dir_id)
        params = urllib.parse.urlencode({
            "$select": "id,code,name",
            "$filter": f"(directoryId eq {self._tags_dir_id})",
            "$orderby": "name asc",
        })
        result = self._request("GET", "/DirectoryEntries", params=params)
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
        return self._request("GET", f"/Issues({task_id})")

    def _format_tags(self, tags: list[Any]) -> list[dict[str, Any]]:
        """Конвертировать строки-UUID в DirectorySetEntry объекты для Timetta API."""
        result = []
        for t in tags:
            if isinstance(t, str):
                result.append({"directoryEntryId": t, "directoryId": self._tags_dir_id})
            elif isinstance(t, dict) and "directoryEntryId" not in t and "id" in t:
                result.append({"directoryEntryId": t["id"], "directoryId": self._tags_dir_id})
            else:
                result.append(t)
        return result

    def update_task(self, task_id: str, **fields: Any) -> dict[str, Any]:
        logger.debug("Updating task %s fields=%s", task_id, list(fields.keys()))
        if "tags" in fields and fields["tags"]:
            fields["tags"] = self._format_tags(fields["tags"])
        return self._request("PATCH", f"/Issues({task_id})", fields)

    def add_comment(self, task_id: str, text: str) -> dict[str, Any] | None:
        logger.debug("Adding comment to task %s (len=%d)", task_id, len(text))
        try:
            return self._request(
                "POST",
                f"/Issues({task_id})/Comments",
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
        url = f"{self.BASE}/Issues({task_id})/Attachments"
        with path.open("rb") as fh:
            content = fh.read()
        boundary = "----TimettaBoundary"
        multipart = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()

        headers = {
            "Authorization": f"Bearer {self._token}",
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
            payload = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404:
                logger.warning("Attachments not supported for Issues — skipping (task=%s)", task_id)
                return None
            logger.error("attach_file failed: %d %s", exc.code, payload)
            raise RuntimeError(f"attach_file {task_id} → {exc.code}: {payload}") from exc
