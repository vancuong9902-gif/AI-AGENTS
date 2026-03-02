from typing import Any

from app.agents.base import BaseAgent
from app.domain.entities.task import Task
from app.tools.executor import ToolExecutor


class ExecutorAgent(BaseAgent):
    role = "executor"

    def __init__(self, tool_executor: ToolExecutor) -> None:
        self._tool_executor = tool_executor

    async def run(self, task: Task, state: dict[str, Any]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for step in state.get("plan", []):
            if step.startswith("tool:"):
                _, tool_name, query = step.split(":", 2)
                results.append(await self._tool_executor.execute(tool_name, {"query": query}))
            else:
                results.append({"step": step, "status": "skipped-no-tool"})
        return {"execution_results": results}
