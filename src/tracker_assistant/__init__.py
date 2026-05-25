# Backward-compatible re-exports.
# Внешний код, использующий `from tracker_assistant import Task, TimettaAdapter`,
# продолжает работать без изменений.
from .timetta.models import Task
from .timetta.adapter import TimettaAdapter
from .timetta.service import list_projects, create_task

__all__ = ["Task", "TimettaAdapter", "list_projects", "create_task"]
