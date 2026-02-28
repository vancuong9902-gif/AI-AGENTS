from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.learner_profile import LearnerProfile

from app.mas.base import AgentContext, BaseAgent
from app.mas.contracts import AgentResult, Event
from app.services.agent_service import build_phase1_document_analysis, generate_exam, grade_exam
from app.services.adaptive_policy_service import recommend_next_action


class ContentAgent(BaseAgent):
    name = "content_agent"

    def __init__(self, db: Session):
        self.db = db

    def handle(self, event: Event, ctx: AgentContext, **kwargs) -> AgentResult:
        # For now: delegate to existing Phase-1 builder.
        if event.type == "DOC_UPLOADED":
            doc_id = int(event.payload.get("document_id"))
            out = build_phase1_document_analysis(self.db, document_id=doc_id, include_llm=bool(event.payload.get("include_llm", True)))
            return AgentResult(agent=self.name, ok=True, output=out)
        return AgentResult(agent=self.name, ok=True, output={"noop": True})


class AssessmentAgent(BaseAgent):
    name = "assessment_agent"

    def __init__(self, db: Session):
        self.db = db

    def handle(self, event: Event, ctx: AgentContext, **kwargs) -> AgentResult:
        if event.type == "PHASE1_COMPLETED":
            req = event.payload
            out = generate_exam(
                self.db,
                user_id=int(req["user_id"]),
                kind=str(req.get("kind") or "entry_test"),
                document_ids=[int(x) for x in (req.get("document_ids") or [])],
                topics=[str(x) for x in (req.get("topics") or [])],
                language=str(req.get("language") or "vi"),
                rag_query=req.get("rag_query"),
            )
            return AgentResult(agent=self.name, ok=True, output=out)

        if event.type in {"ENTRY_TEST_SUBMITTED", "TOPIC_EXERCISE_SUBMITTED", "FINAL_EXAM_SUBMITTED"}:
            req = event.payload
            out = grade_exam(
                self.db,
                quiz_id=int(req["quiz_id"]),
                user_id=int(req["user_id"]),
                duration_sec=int(req.get("duration_sec") or 0),
                answers=list(req.get("answers") or []),
            )
            return AgentResult(agent=self.name, ok=True, output=out)

        return AgentResult(agent=self.name, ok=True, output={"noop": True})


class AdaptivePolicyAgent(BaseAgent):
    name = "adaptive_policy_agent"

    def __init__(self, db: Session):
        self.db = db

    def handle(self, event: Event, ctx: AgentContext, **kwargs) -> AgentResult:
        if event.type in {"ENTRY_TEST_SUBMITTED", "TOPIC_EXERCISE_SUBMITTED"}:
            req = event.payload
            out = recommend_next_action(
                self.db,
                user_id=int(req["user_id"]),
                document_id=req.get("document_id"),
                topic=req.get("topic"),
                last_attempt_id=req.get("attempt_id"),
                recent_accuracy=req.get("recent_accuracy"),
                avg_time_per_item_sec=req.get("avg_time_per_item_sec"),
                engagement=req.get("engagement"),
                current_difficulty=req.get("current_difficulty"),
                policy_type=str(req.get("policy_type") or "contextual_bandit"),
                epsilon=float(req.get("epsilon") or 0.08),
            )
            return AgentResult(agent=self.name, ok=True, output=out)
        return AgentResult(agent=self.name, ok=True, output={"noop": True})




class LearnerModelingAgent(BaseAgent):
    name = "learner_modeling_agent"

    def __init__(self, db: Session):
        self.db = db

    def handle(self, event: Event, ctx: AgentContext, **kwargs) -> AgentResult:
        if event.type in {"ENTRY_TEST_SUBMITTED", "TOPIC_EXERCISE_SUBMITTED", "FINAL_EXAM_SUBMITTED"}:
            uid = int(event.user_id)
            prof = self.db.query(LearnerProfile).filter(LearnerProfile.user_id == uid).first()
            if not prof:
                return AgentResult(agent=self.name, ok=True, output={"user_id": uid, "level": "beginner", "topic_mastery": {}, "topic_stats": {}})
            mj = prof.mastery_json or {}
            out = {
                "user_id": uid,
                "level": str(prof.level or "beginner"),
                "difficulty_prior": str((mj.get("difficulty") or "easy")),
                "topic_mastery": mj.get("topic_mastery") if isinstance(mj.get("topic_mastery"), dict) else {},
                "topic_stats": mj.get("topic_stats") if isinstance(mj.get("topic_stats"), dict) else {},
            }
            return AgentResult(agent=self.name, ok=True, output=out)
        return AgentResult(agent=self.name, ok=True, output={"noop": True})

class EvaluationAnalyticsAgent(BaseAgent):
    name = "evaluation_analytics_agent"

    def __init__(self, db: Session):
        self.db = db

    def handle(self, event: Event, ctx: AgentContext, **kwargs) -> AgentResult:
        # Placeholder: analytics already implemented in agent_service.final_exam_analytics.
        return AgentResult(agent=self.name, ok=True, output={"note": "analytics handled in agent_service"})
