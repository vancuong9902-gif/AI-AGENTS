from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class LLMProviderInterface(ABC):
    @abstractmethod
    async def generate(self, prompt: str, *, model: str) -> str: ...

    @abstractmethod
    async def stream(self, prompt: str, *, model: str) -> AsyncIterator[str]: ...

    @abstractmethod
    async def structured_output(self, prompt: str, schema: dict[str, Any], *, model: str) -> dict[str, Any]: ...

    @abstractmethod
    async def embeddings(self, texts: list[str], *, model: str) -> list[list[float]]: ...
