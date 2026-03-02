from typing import Any

from app.agents.base import BaseAgent
from app.domain.entities.task import Task
from app.domain.interfaces.memory_interface import MemoryInterface


class MemoryAgent(BaseAgent):
    role = "memory"

    def __init__(self, memory: MemoryInterface) -> None:
        self._memory = memory

    async def run(self, task: Task, state: dict[str, Any]) -> dict[str, Any]:
        await self._memory.store("episodic", task.id, {"objective": task.objective, "state": state})
        digest = await self._memory.summarize("episodic")
        return {"memory_digest": digest}
