from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


OrchestratorStatus = Literal["OK", "NEED_CLEAN_TEXT", "NEED_MORE_INFO", "ERROR"]


class OrchestratorResponse(BaseModel):
    """Strict response envelope for AI Learning Orchestrator frontend integration."""

    status: OrchestratorStatus
    action: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=500)
    data: Dict[str, Any] = Field(default_factory=dict)
    next_steps: List[str] = Field(default_factory=list)
