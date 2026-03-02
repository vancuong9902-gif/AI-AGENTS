from abc import ABC, abstractmethod
from typing import Any

from app.domain.entities.task import Task


class BaseAgent(ABC):
    role: str

    @abstractmethod
    async def run(self, task: Task, state: dict[str, Any]) -> dict[str, Any]: ...
