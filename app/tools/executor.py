import asyncio
from typing import Any

from app.guardrails.policies import validate_payload_against_schema
from app.tools.registry import ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, timeout_s: float = 10.0) -> None:
        self._registry = registry
        self._timeout_s = timeout_s

    async def execute(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        spec = self._registry.get(tool_name)
        validate_payload_against_schema(payload, spec.schema)
        result = await asyncio.wait_for(spec.handler(payload), timeout=self._timeout_s)
        return {"tool": tool_name, "status": "ok", "result": result}
