from app.agents.base import BaseAgent
from app.domain.entities.task import Task


class ResearchAgent(BaseAgent):
    role = "research"

    async def run(self, task: Task, state: dict[str, object]) -> dict[str, object]:
        return {"research_notes": [f"Research placeholder for: {task.objective}"]}
