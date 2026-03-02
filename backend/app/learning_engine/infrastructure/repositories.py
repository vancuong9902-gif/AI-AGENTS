from __future__ import annotations

from collections import defaultdict

from app.learning_engine.domain.models import EntranceTestQuestion, LearningPathStep, PerformanceReport, ProgressSnapshot, Topic
from app.learning_engine.domain.ports import AssessmentRepository, TopicRepository


class InMemoryTopicRepository(TopicRepository):
    def __init__(self) -> None:
        self._by_document: dict[str, list[Topic]] = defaultdict(list)

    async def save_topics(self, document_id: str, topics: list[Topic]) -> None:
        self._by_document[document_id] = topics

    async def list_topics(self, document_id: str, page: int, page_size: int) -> list[Topic]:
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        start = (page - 1) * page_size
        end = start + page_size
        return self._by_document.get(document_id, [])[start:end]


class InMemoryAssessmentRepository(AssessmentRepository):
    def __init__(self) -> None:
        self.tests: dict[str, list[EntranceTestQuestion]] = defaultdict(list)
        self.paths: dict[str, list[LearningPathStep]] = defaultdict(list)
        self.progress: dict[str, ProgressSnapshot] = {}
        self.reports: dict[str, PerformanceReport] = {}

    async def save_entrance_test(self, student_id: str, questions: list[EntranceTestQuestion]) -> None:
        self.tests[student_id] = questions

    async def save_learning_path(self, student_id: str, steps: list[LearningPathStep]) -> None:
        self.paths[student_id] = steps

    async def save_progress(self, snapshot: ProgressSnapshot) -> None:
        self.progress[snapshot.student_id] = snapshot

    async def save_final_report(self, report: PerformanceReport) -> None:
        self.reports[report.student_id] = report
