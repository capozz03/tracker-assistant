from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..models import Task

logger = logging.getLogger(__name__)

_ORG_HEADERS = {
    "cloud": "X-Cloud-Org-ID",
    "yandex": "X-Org-ID",
}


class YandexTrackerAdapter:
    BASE = "https://api.tracker.yandex.net/v3"

    def __init__(self, token: str, org_id: str, org_type: str = "cloud") -> None:
        self._token = token
        self._org_id = org_id
        self._org_header = _ORG_HEADERS.get(org_type, "X-Cloud-Org-ID")

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        url = f"{self.BASE}{path}"
        headers = {
            "Authorization": f"OAuth {self._token}",
            self._org_header: self._org_id,
            "Content-Type": "application/json; charset=utf-8",
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
            logger.error("← %s %s status=%d body=%s", method, path, exc.code, payload)
            raise RuntimeError(f"Yandex Tracker {method} {path} → {exc.code}: {payload}") from exc

    def get_projects(self) -> list[dict[str, Any]]:
        logger.debug("Fetching projects (paginated)")
        projects: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = self._request("GET", f"/projects?perPage=50&page={page}")
            if not batch:
                break
            projects.extend(batch)
            logger.debug("Page %d: got %d projects", page, len(batch))
            if len(batch) < 50:
                break
            page += 1
        logger.debug("Total projects fetched: %d", len(projects))
        return projects

    def create_issue(self, task: Task) -> dict[str, Any]:
        body = task.to_api_body()
        logger.debug("Creating issue: queue=%s summary=%r", task.queue, task.summary)
        result = self._request("POST", "/issues", body)
        logger.debug("Created issue key=%s", result.get("key"))
        return result

    def add_comment(self, issue_key: str, text: str) -> dict[str, Any]:
        logger.debug("Adding comment to %s (len=%d)", issue_key, len(text))
        return self._request("POST", f"/issues/{issue_key}/comments", {"text": text})

    def attach_file(self, issue_key: str, filepath: str) -> dict[str, Any]:
        path = Path(filepath)
        logger.debug("Attaching file %s to %s", path.name, issue_key)
        url = f"{self.BASE}/issues/{issue_key}/attachments"
        headers = {
            "Authorization": f"OAuth {self._token}",
            self._org_header: self._org_id,
        }
        with path.open("rb") as fh:
            content = fh.read()
        boundary = "----TrackerBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        req = urllib.request.Request(url=url, method="POST", headers=headers, data=body)
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8").strip()
                result = json.loads(raw) if raw else {}
                logger.debug("Attached file %s to %s", path.name, issue_key)
                return result
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            logger.error("Attach file failed: %d %s", exc.code, payload)
            raise RuntimeError(f"attach_file {issue_key} → {exc.code}: {payload}") from exc

    def get_issue(self, issue_key: str) -> dict[str, Any]:
        logger.debug("Getting issue %s", issue_key)
        return self._request("GET", f"/issues/{issue_key}")

    def update_issue(self, issue_key: str, **fields: Any) -> dict[str, Any]:
        logger.debug("Updating issue %s fields=%s", issue_key, list(fields.keys()))
        return self._request("PATCH", f"/issues/{issue_key}", fields)
