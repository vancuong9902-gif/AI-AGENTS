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


def test_pipeline_end_to_end() -> None:
    async def _run() -> None:
        async def search(payload: dict[str, str]) -> dict[str, str]:
            return {"doc": payload["query"]}

        async def codegen(payload: dict[str, str]) -> dict[str, str]:
            return {"file": payload["query"]}

        registry = ToolRegistry()
        registry.register(ToolSpec(name="search", schema={"required": ["query"]}, handler=search))
        registry.register(ToolSpec(name="codegen", schema={"required": ["query"]}, handler=codegen))

        orchestrator = MultiAgentOrchestrator(
            AgentBundle(
                planner=PlannerAgent(MockLLMProvider(), model="mock"),
                executor=ExecutorAgent(ToolExecutor(registry)),
                critic=CriticAgent(),
                memory=MemoryAgent(InMemoryBackend()),
                coordinator=CoordinatorAgent(),
            ),
            StructuredLogger("test"),
            MetricsCollector(),
        )

        result = await orchestrator.run(Task(id="t1", objective="Build architecture"))
        assert result["task_status"] == "completed"
        assert result["state"]["approved"] is True

    asyncio.run(_run())
