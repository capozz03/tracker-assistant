from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Task:
    project_id: str              # ID проекта в Timetta (обязательно)
    summary: str                 # название задачи (обязательно)
    description: str = ""
    task_type: str = ""          # тип задачи (опционально)
    assignee: str = ""           # login или ID исполнителя
    tags: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    attachments: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    def to_api_body(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "projectId": self.project_id,
            "name": self.summary,
        }
        if self.description:
            body["description"] = self.description
        if self.task_type:
            body["typeId"] = self.task_type
        if self.assignee:
            body["assigneeId"] = self.assignee
        if self.tags:
            body["tags"] = self.tags
        body.update(self.extra)
        return body
