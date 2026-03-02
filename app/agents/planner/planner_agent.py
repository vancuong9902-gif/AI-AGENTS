from typing import Any

from app.agents.base import BaseAgent
from app.domain.entities.task import Task
from app.domain.interfaces.llm_provider_interface import LLMProviderInterface


class PlannerAgent(BaseAgent):
    role = "planner"

    def __init__(self, llm: LLMProviderInterface, model: str) -> None:
        self._llm = llm
        self._model = model

    async def run(self, task: Task, state: dict[str, Any]) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                }
            },
            "required": ["steps"],
            "additionalProperties": False,
        }
        prompt = (
            "Decompose objective into concrete executable steps. "
            f"Objective: {task.objective}. Existing context keys: {list(task.context.keys())}"
        )
        plan = await self._llm.structured_output(prompt, schema, model=self._model)
        return {"plan": plan["steps"]}
