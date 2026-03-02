import asyncio

from app.agents.coordinator.coordinator_agent import CoordinatorAgent
from app.agents.critic.critic_agent import CriticAgent
from app.agents.executor import ExecutorAgent
from app.agents.memory.memory_agent import MemoryAgent
from app.agents.planner.planner_agent import PlannerAgent
from app.application.orchestrators.multi_agent_orchestrator import AgentBundle, MultiAgentOrchestrator
from app.domain.entities.task import Task
from app.infrastructure.logging.structured_logger import StructuredLogger
from app.infrastructure.monitoring.metrics import MetricsCollector
from app.llm.mock_provider import MockLLMProvider
from app.memory.in_memory import InMemoryBackend
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry, ToolSpec


async def _search_tool(payload: dict[str, str]) -> dict[str, str]:
    return {"hit": f"result for {payload['query']}"}


async def _codegen_tool(payload: dict[str, str]) -> dict[str, str]:
    return {"artifact": f"generated module for {payload['query']}"}


async def main() -> None:
    registry = ToolRegistry()
    registry.register(ToolSpec(name="search", schema={"required": ["query"]}, handler=_search_tool))
    registry.register(ToolSpec(name="codegen", schema={"required": ["query"]}, handler=_codegen_tool))

    agents = AgentBundle(
        planner=PlannerAgent(MockLLMProvider(), model="mock-1"),
        executor=ExecutorAgent(ToolExecutor(registry)),
        critic=CriticAgent(),
        memory=MemoryAgent(InMemoryBackend()),
        coordinator=CoordinatorAgent(),
    )
    orchestrator = MultiAgentOrchestrator(agents, StructuredLogger("mas"), MetricsCollector())
    result = await orchestrator.run(Task(id="demo-1", objective="Design enterprise AI architecture"))
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
