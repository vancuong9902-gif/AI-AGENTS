from __future__ import annotations

from dataclasses import dataclass

from app.learning_engine.domain.models import EntranceTestQuestion, LearningPathStep, PerformanceReport, ProgressSnapshot, StudentLevel, Topic
from app.learning_engine.domain.ports import LLMPort, VectorIndexPort


@dataclass(slots=True)
class TopicExtractionAgent:
    llm: LLMPort

    async def run(self, text: str) -> list[Topic]:
        payload = await self.llm.generate_json(
            "You extract pedagogically-coherent topics from educational material.",
            f"Extract topics from content and provide: title, summary, difficulty(0..1), keywords.\n{text[:12000]}",
        )
        return [
            Topic(
                id=f"topic-{idx+1}",
                title=item["title"],
                summary=item.get("summary", ""),
                difficulty=float(item.get("difficulty", 0.5)),
                keywords=item.get("keywords", []),
            )
            for idx, item in enumerate(payload.get("topics", []))
        ]


@dataclass(slots=True)
class AssessmentAgent:
    llm: LLMPort

    async def build_entrance_test(self, topics: list[Topic], question_count: int = 12) -> list[EntranceTestQuestion]:
        payload = await self.llm.generate_json(
            "You build adaptive entrance tests for AI Teacher platform.",
            f"Create {question_count} mixed-difficulty MCQs from these topics: {[t.title for t in topics]}",
        )
        return [
            EntranceTestQuestion(
                id=q["id"],
                topic_id=q["topic_id"],
                stem=q["stem"],
                choices=q["choices"],
                answer_index=int(q["answer_index"]),
                difficulty=float(q.get("difficulty", 0.5)),
            )
            for q in payload.get("questions", [])
        ]

    async def evaluate_level(self, score: float) -> StudentLevel:
        if score < 0.4:
            return StudentLevel.beginner
        if score < 0.75:
            return StudentLevel.intermediate
        return StudentLevel.advanced


@dataclass(slots=True)
class LearningPathAgent:
    llm: LLMPort

    async def build_path(self, level: StudentLevel, topics: list[Topic]) -> list[LearningPathStep]:
        payload = await self.llm.generate_json(
            "You design personalized learning path based on learner level and topic graph.",
            f"Student level: {level.value}. Topics: {[t.title for t in topics]}",
        )
        return [
            LearningPathStep(
                order=int(step["order"]),
                topic_id=step["topic_id"],
                objective=step["objective"],
                exercise_count=int(step.get("exercise_count", 3)),
            )
            for step in payload.get("steps", [])
        ]


@dataclass(slots=True)
class ExerciseAgent:
    llm: LLMPort
    vector_index: VectorIndexPort

    async def generate(self, topic_id: str, objective: str, difficulty: str) -> dict:
        contexts = await self.vector_index.semantic_search(f"{topic_id} {objective}")
        return await self.llm.generate_json(
            "You create dynamic exercises grounded in retrieved context.",
            f"Difficulty={difficulty}; objective={objective}; contexts={contexts}",
        )


@dataclass(slots=True)
class ReportingAgent:
    llm: LLMPort

    async def build_report(self, student_id: str, level: StudentLevel, progress: ProgressSnapshot, exam_score: float) -> PerformanceReport:
        payload = await self.llm.generate_json(
            "You are an academic analyst generating concise performance reports.",
            f"student={student_id}, level={level.value}, progress={progress.mastery_by_topic}, exam_score={exam_score}",
        )
        return PerformanceReport(
            student_id=student_id,
            level=level,
            strengths=payload.get("strengths", []),
            weaknesses=payload.get("weaknesses", []),
            recommendations=payload.get("recommendations", []),
            metrics={"completion_rate": progress.completion_rate, "exam_score": exam_score},
        )
