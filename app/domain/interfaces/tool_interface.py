from abc import ABC, abstractmethod
from typing import Any


class ToolInterface(ABC):
    name: str
    schema: dict[str, Any]

    @abstractmethod
    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]: ...
