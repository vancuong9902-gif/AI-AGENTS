from app.agents.base import BaseAgent
from app.domain.entities.task import Task


class CoderAgent(BaseAgent):
    role = "coder"

    async def run(self, task: Task, state: dict[str, object]) -> dict[str, object]:
        return {"code_patch": "# placeholder patch"}
