from __future__ import annotations

from dataclasses import dataclass

from app.learning_engine.application.agents import AssessmentAgent, ExerciseAgent, LearningPathAgent, ReportingAgent, TopicExtractionAgent
from app.learning_engine.domain.models import ProgressSnapshot, StudentLevel
from app.learning_engine.domain.ports import AssessmentRepository, TopicRepository, VectorIndexPort


@dataclass(slots=True)
class LearningOrchestratorService:
    topic_repo: TopicRepository
    assessment_repo: AssessmentRepository
    vector_index: VectorIndexPort
    topic_agent: TopicExtractionAgent
    assessment_agent: AssessmentAgent
    path_agent: LearningPathAgent
    exercise_agent: ExerciseAgent
    reporting_agent: ReportingAgent

    async def ingest_document(self, document_id: str, content: str) -> list[dict]:
        topics = await self.topic_agent.run(content)
        await self.topic_repo.save_topics(document_id, topics)
        await self.vector_index.upsert_document_chunks(document_id, [t.summary for t in topics if t.summary])
        return [t.__dict__ for t in topics]

    async def build_entrance_assessment(self, student_id: str, document_id: str) -> list[dict]:
        topics = await self.topic_repo.list_topics(document_id=document_id, page=1, page_size=100)
        questions = await self.assessment_agent.build_entrance_test(topics)
        await self.assessment_repo.save_entrance_test(student_id, questions)
        return [q.__dict__ for q in questions]

    async def evaluate_and_generate_path(self, student_id: str, document_id: str, score: float) -> dict:
        level = await self.assessment_agent.evaluate_level(score)
        topics = await self.topic_repo.list_topics(document_id=document_id, page=1, page_size=100)
        steps = await self.path_agent.build_path(level, topics)
        await self.assessment_repo.save_learning_path(student_id, steps)
        return {"level": level.value, "steps": [s.__dict__ for s in steps]}

    async def generate_exercise(self, topic_id: str, objective: str, difficulty: str) -> dict:
        return await self.exercise_agent.generate(topic_id, objective, difficulty)

    async def update_progress(self, student_id: str, completion_rate: float, mastery_by_topic: dict[str, float]) -> dict:
        snapshot = ProgressSnapshot(student_id=student_id, completion_rate=completion_rate, mastery_by_topic=mastery_by_topic)
        await self.assessment_repo.save_progress(snapshot)
        return {"student_id": student_id, "completion_rate": completion_rate}

    async def create_final_report(self, student_id: str, level: str, completion_rate: float, mastery_by_topic: dict[str, float], exam_score: float):
        snapshot = ProgressSnapshot(student_id=student_id, completion_rate=completion_rate, mastery_by_topic=mastery_by_topic)
        report = await self.reporting_agent.build_report(student_id, level=StudentLevel(level), progress=snapshot, exam_score=exam_score)
        await self.assessment_repo.save_final_report(report)
        return report.__dict__
