from typing import Any

from app.agents.base import BaseAgent
from app.domain.entities.task import Task


class CriticAgent(BaseAgent):
    role = "critic"

    async def run(self, task: Task, state: dict[str, Any]) -> dict[str, Any]:
        failures = [r for r in state.get("execution_results", []) if r.get("status") != "ok"]
        return {
            "approved": len(failures) == 0,
            "issues": failures,
            "summary": "Execution approved" if not failures else "Execution needs retry",
        }
