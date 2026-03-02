from collections import defaultdict
from typing import Any

from app.domain.interfaces.memory_interface import MemoryInterface


class InMemoryBackend(MemoryInterface):
    def __init__(self) -> None:
        self._db: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    async def store(self, namespace: str, key: str, value: dict[str, Any]) -> None:
        self._db[namespace][key] = value

    async def retrieve(self, namespace: str, key: str) -> dict[str, Any] | None:
        return self._db[namespace].get(key)

    async def summarize(self, namespace: str, limit: int = 20) -> str:
        keys = list(self._db[namespace].keys())[-limit:]
        return f"{namespace} contains {len(keys)} records: {keys}"

    async def delete(self, namespace: str, key: str) -> None:
        self._db[namespace].pop(key, None)
