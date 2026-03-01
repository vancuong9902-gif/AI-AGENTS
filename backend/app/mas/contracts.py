from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, field_validator


EventType = Literal[
    "DOC_UPLOADED",
    "PHASE1_COMPLETED",
    "ENTRY_TEST_SUBMITTED",
    "TOPIC_EXERCISE_SUBMITTED",
    "FINAL_EXAM_SUBMITTED",
    "POLICY_TICK",
]


class Event(BaseModel):
    """A minimal event contract used by the MAS orchestrator.

    The system can be run in either:
      - request/response mode: a single API call triggers a deterministic chain, OR
      - event-driven mode: events are appended to a log/queue and consumed asynchronously.
    """

    type: str
    payload: Dict[str, Any] = {}
    user_id: Optional[int] = None
    trace_id: Optional[str] = None

    @field_validator("type")
    @classmethod
    def type_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Event type cannot be empty")
        return v.upper().strip()


@dataclass
class AgentResult:
    agent: str
    ok: bool
    output: Dict[str, Any]
    warnings: List[str] | None = None
    error: Optional[str] = None


@dataclass
class OrchestratorDecision:
    """The orchestrator emits a high-level decision to the UI."""

    next_step: str
    recommended_action: str
    difficulty: str
    debug: Dict[str, Any]
