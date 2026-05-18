from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Task:
    queue: str
    summary: str
    project_id: str = ""
    description: str = ""
    issue_type: str = "task"
    tags: list[str] = field(default_factory=list)
    assignee: str = ""
    followers: list[str] = field(default_factory=list)
    parent: str = ""
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
            "queue": self.queue,
            "summary": self.summary,
            "type": self.issue_type,
        }
        if self.description:
            body["description"] = self.description
        if self.project_id:
            body["project"] = {"primary": int(self.project_id)}
        if self.tags:
            body["tags"] = self.tags
        if self.assignee:
            body["assignee"] = self.assignee
        if self.followers:
            body["followers"] = self.followers
        if self.parent:
            body["parent"] = self.parent
        body.update(self.extra)
        return body
