from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.mas.base import AgentContext
from app.mas.contracts import AgentResult, Event, OrchestratorDecision
from app.mas.agents import AssessmentAgent, ContentAgent, AdaptivePolicyAgent, LearnerModelingAgent, EvaluationAnalyticsAgent


class Orchestrator:
    """Thin orchestrator coordinating multiple specialized agents.

    This is a minimal reference implementation intended for research prototyping.
    """

    def __init__(self, db: Session):
        self.db = db
        self.content = ContentAgent(db)
        self.assessment = AssessmentAgent(db)
        self.policy = AdaptivePolicyAgent(db)
        self.modeling = LearnerModelingAgent(db)
        self.analytics = EvaluationAnalyticsAgent(db)

    def run(self, event: Event, ctx: AgentContext) -> Dict[str, Any]:
        """Run a short agent chain based on the incoming event."""

        trace: List[AgentResult] = []

        if event.type == "DOC_UPLOADED":
            r1 = self.content.handle(event, ctx)
            trace.append(r1)
            if not r1.ok:
                return {"ok": False, "trace": [t.__dict__ for t in trace]}
            # Next step suggestion: generate entry test.
            dec = OrchestratorDecision(
                next_step="ENTRY_TEST",
                recommended_action="continue",
                difficulty="easy",
                debug={"reason": "start_diagnostic"},
            )
            return {"ok": True, "trace": [t.__dict__ for t in trace], "decision": dec.__dict__}

        if event.type in {"PHASE1_COMPLETED", "ENTRY_TEST_SUBMITTED", "TOPIC_EXERCISE_SUBMITTED"}:
            r1 = self.assessment.handle(event, ctx)
            trace.append(r1)
            if not r1.ok:
                return {"ok": False, "trace": [t.__dict__ for t in trace]}
            # After grading: refresh learner model snapshot (K_t) then ask policy.
            r_model = self.modeling.handle(event, ctx)
            trace.append(r_model)

            pol_event = Event(
                type=event.type,
                user_id=event.user_id,
                payload={
                    **event.payload,
                    "recent_accuracy": float((r1.output.get("score_percent") or 0) / 100.0) if isinstance(r1.output, dict) else None,
                    "topic_mastery": (r_model.output or {}).get("topic_mastery") if isinstance(r_model.output, dict) else {},
                    "current_difficulty": ((r_model.output or {}).get("difficulty_prior") if isinstance(r_model.output, dict) else None),
                },
            )
            r2 = self.policy.handle(pol_event, ctx)
            trace.append(r2)


            dec = OrchestratorDecision(
                next_step="TOPIC_LOOP",
                recommended_action=str((r2.output or {}).get("recommended_action") or "continue"),
                difficulty=str((r2.output or {}).get("recommended_difficulty") or "easy"),
                debug={"policy": r2.output},
            )
            return {"ok": True, "trace": [t.__dict__ for t in trace], "decision": dec.__dict__}

        return {"ok": True, "trace": [], "decision": {"next_step": "NOOP", "recommended_action": "continue", "difficulty": "easy", "debug": {}}}
