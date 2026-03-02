import asyncio

import pytest

from app.guardrails.policies import GuardrailViolation
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry, ToolSpec


def test_tool_schema_validation() -> None:
    async def _run() -> None:
        async def tool(payload: dict[str, str]) -> dict[str, str]:
            return payload

        registry = ToolRegistry()
        registry.register(ToolSpec(name="demo", schema={"required": ["query"]}, handler=tool))

        executor = ToolExecutor(registry)
        with pytest.raises(GuardrailViolation):
            await executor.execute("demo", {"q": "missing field"})

    asyncio.run(_run())
