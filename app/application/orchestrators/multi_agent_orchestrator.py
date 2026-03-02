from dataclasses import dataclass
from time import perf_counter
from typing import Any

from app.agents.coordinator.coordinator_agent import CoordinatorAgent
from app.agents.critic.critic_agent import CriticAgent
from app.agents.executor import ExecutorAgent
from app.agents.memory.memory_agent import MemoryAgent
from app.agents.planner.planner_agent import PlannerAgent
from app.domain.entities.task import Task
from app.infrastructure.logging.structured_logger import StructuredLogger
from app.infrastructure.monitoring.metrics import MetricsCollector
from app.infrastructure.monitoring.resilience import CircuitBreaker, retry_with_backoff


@dataclass
class AgentBundle:
    planner: PlannerAgent
    executor: ExecutorAgent
    critic: CriticAgent
    memory: MemoryAgent
    coordinator: CoordinatorAgent


class MultiAgentOrchestrator:
    def __init__(self, agents: AgentBundle, logger: StructuredLogger, metrics: MetricsCollector) -> None:
        self._agents = agents
        self._logger = logger
        self._metrics = metrics
        self._breaker = CircuitBreaker(failure_threshold=3)

    async def run(self, task: Task) -> dict[str, Any]:
        state: dict[str, Any] = {}
        start = perf_counter()

        async def guarded_plan() -> dict[str, Any]:
            return await self._agents.planner.run(task, state)

        plan = await retry_with_backoff(lambda: self._breaker.call(guarded_plan))
        state.update(plan)
        state.update(await self._agents.executor.run(task, state))
        state.update(await self._agents.critic.run(task, state))
        state.update(await self._agents.memory.run(task, state))
        final = await self._agents.coordinator.finalize(task, state)

        self._metrics.inc("tasks.total")
        self._metrics.inc(f"tasks.{final['task_status']}")
        self._logger.info(
            "task.completed",
            task_id=task.id,
            status=final["task_status"],
            latency_ms=int((perf_counter() - start) * 1000),
        )
        return final
