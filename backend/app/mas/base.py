from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.mas.contracts import AgentResult, Event


@dataclass
class AgentContext:
    """Shared context passed between agents.

    In a production MAS, this would include:
      - a read-only view of learner state K_t
      - active document/topic scope
      - RAG cache / retrieval handles
      - rate-limit and budget managers
    """

    user_id: int
    document_ids: List[int] = field(default_factory=list)
    topic: Optional[str] = None
    memory: Dict[str, Any] = field(default_factory=dict)


class BaseAgent:
    """Abstract agent.

    Agents are pure functions over (event, context) with internal state maintained
    in persistent storage (DB) rather than local process memory.
    """

    name: str = "base"

    def handle(self, event: Event, ctx: AgentContext, **kwargs) -> AgentResult:  # pragma: no cover
        raise NotImplementedError
