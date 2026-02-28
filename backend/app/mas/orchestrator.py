from __future__ import annotations

import time
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.core.config import settings
from app.infra.event_bus import RedisEventBus
from app.mas.base import AgentContext
from app.mas.contracts import AgentResult, Event, OrchestratorDecision
from app.mas.agents import AssessmentAgent, ContentAgent, AdaptivePolicyAgent, LearnerModelingAgent, EvaluationAnalyticsAgent
from app.models.agent_log import AgentLog


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
        self.event_bus = RedisEventBus(settings.REDIS_URL)

    def _publish_event(self, event: Event) -> str:
        try:
            return self.event_bus.publish(event_type=event.type, payload=event.payload, user_id=str(event.user_id))
        except Exception:
            return str(getattr(event, "trace_id", "") or f"local-{int(time.time() * 1000)}")

    def _execute_and_log(self, *, event: Event, event_id: str, trace: List[AgentResult], agent_name: str, agent_fn) -> AgentResult:
        started = time.perf_counter()
        status = "success"
        result: AgentResult | None = None
        try:
            result = agent_fn(event)
            status = "success" if result.ok else "failed"
        except TimeoutError:
            status = "timeout"
            result = AgentResult(agent=agent_name, ok=False, output={}, error="timeout")
        except Exception:
            status = "failed"
            result = AgentResult(agent=agent_name, ok=False, output={}, error="execution_error")
        finally:
            duration_ms = int((time.perf_counter() - started) * 1000)
            if result is not None:
                log_row = AgentLog(
                    event_id=event_id,
                    event_type=event.type,
                    agent_name=result.agent,
                    user_id=int(event.user_id) if getattr(event, "user_id", None) is not None else None,
                    input_payload=event.payload or {},
                    output_summary=result.output or {},
                    status=status,
                    duration_ms=duration_ms,
                )
                self.db.add(log_row)
                self.db.commit()
                trace.append(result)

        assert result is not None
        return result

    def run(self, event: Event, ctx: AgentContext) -> Dict[str, Any]:
        """Run a short agent chain based on the incoming event."""

        trace: List[AgentResult] = []
        event_id = self._publish_event(event)

        if event.type == "DOC_UPLOADED":
            r1 = self._execute_and_log(event=event, event_id=event_id, trace=trace, agent_name="content_agent", agent_fn=lambda e: self.content.handle(e, ctx))
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
            r1 = self._execute_and_log(event=event, event_id=event_id, trace=trace, agent_name="assessment_agent", agent_fn=lambda e: self.assessment.handle(e, ctx))
            if not r1.ok:
                return {"ok": False, "trace": [t.__dict__ for t in trace]}
            # After grading: refresh learner model snapshot (K_t) then ask policy.
            r_model = self._execute_and_log(event=event, event_id=event_id, trace=trace, agent_name="learner_modeling_agent", agent_fn=lambda e: self.modeling.handle(e, ctx))

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
            r2 = self._execute_and_log(event=pol_event, event_id=event_id, trace=trace, agent_name="adaptive_policy_agent", agent_fn=lambda e: self.policy.handle(e, ctx))


            dec = OrchestratorDecision(
                next_step="TOPIC_LOOP",
                recommended_action=str((r2.output or {}).get("recommended_action") or "continue"),
                difficulty=str((r2.output or {}).get("recommended_difficulty") or "easy"),
                debug={"policy": r2.output},
            )
            return {"ok": True, "trace": [t.__dict__ for t in trace], "decision": dec.__dict__}

        return {"ok": True, "trace": [], "decision": {"next_step": "NOOP", "recommended_action": "continue", "difficulty": "easy", "debug": {}}}
