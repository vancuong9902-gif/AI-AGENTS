from typing import Any

from app.domain.entities.task import Task
from app.domain.entities.task import TaskStatus


class CoordinatorAgent:
    async def finalize(self, task: Task, state: dict[str, Any]) -> dict[str, Any]:
        task.status = TaskStatus.COMPLETED if state.get("approved") else TaskStatus.FAILED
        return {"task_status": task.status.value, "state": state}
