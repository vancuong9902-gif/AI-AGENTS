from abc import ABC, abstractmethod
from typing import Any


class MemoryInterface(ABC):
    @abstractmethod
    async def store(self, namespace: str, key: str, value: dict[str, Any]) -> None: ...

    @abstractmethod
    async def retrieve(self, namespace: str, key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    async def summarize(self, namespace: str, limit: int = 20) -> str: ...

    @abstractmethod
    async def delete(self, namespace: str, key: str) -> None: ...
