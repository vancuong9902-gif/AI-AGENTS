from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.lms import router
from app.db.session import get_db
from app.models.document_topic import DocumentTopic
from app.models.learner_profile import LearnerProfile
from app.models.learning_plan import LearningPlan
from app.models.quiz_set import QuizSet
from app.services.lms_service import assign_learning_path


class FakeQuery:
    def __init__(self, db: "FakeSession", model):
        self.db = db
        self.model = model

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        if self.model is DocumentTopic:
            return list(self.db.document_topics)
        return []

    def first(self):
        if self.model is QuizSet:
            if self.db.quiz_calls < len(self.db.quiz_sequence):
                item = self.db.quiz_sequence[self.db.quiz_calls]
                self.db.quiz_calls += 1
                return item
            return self.db.quiz_fallback
        if self.model is LearnerProfile:
            return self.db.profile
        if self.model is LearningPlan:
            return self.db.plans[-1] if self.db.plans else None
        return None


class FakeSession:
    def __init__(self, topics=None, quiz_sequence=None, quiz_fallback=None, profile=None):
        self.document_topics = topics or []
        self.quiz_sequence = quiz_sequence or []
        self.quiz_fallback = quiz_fallback
        self.quiz_calls = 0
        self.profile = profile
        self.plans = []
        self._plan_id = 1

    def query(self, model):
        return FakeQuery(self, model)

    def add(self, obj):
        if isinstance(obj, LearnerProfile):
            self.profile = obj
        if isinstance(obj, LearningPlan):
            if not getattr(obj, "id", None):
                obj.id = self._plan_id
                self._plan_id += 1
            self.plans.append(obj)

    def commit(self):
        return None

    def refresh(self, _obj):
        return None


def _topic(topic_id: int, title: str, doc_id: int, body_len: int):
    t = DocumentTopic(id=topic_id, title=title, document_id=doc_id, topic_index=topic_id, summary="x" * body_len, keywords=[])
    t.body_len = body_len
    return t


def _quiz(quiz_id: int, level: str):
    return QuizSet(id=quiz_id, user_id=1, topic="topic", level=level, kind="quiz")


def test_assign_level_yeu_prefers_short_topics_and_beginner_quiz():
    topics = [
        _topic(1, "Dai so nang cao", 11, 3400),
        _topic(2, "Can ban phep cong", 11, 500),
        _topic(3, "Can ban phep tru", 11, 800),
        _topic(4, "Can ban phep nhan", 11, 1200),
    ]
    beginner_quiz = _quiz(101, "beginner")
    db = FakeSession(topics=topics, quiz_sequence=[beginner_quiz, beginner_quiz, beginner_quiz], quiz_fallback=beginner_quiz)

    result = assign_learning_path(db, user_id=2, student_level="yeu", document_ids=[11], classroom_id=9)

    assert result["total_assigned"] == 3
    assert [x["id"] for x in result["assigned_topics"]] == [2, 3, 4]
    assert all(q["level"] == "beginner" for q in result["assigned_quizzes"])


def test_assign_level_gioi_selects_all_topics():
    topics = [_topic(1, "A", 1, 1000), _topic(2, "B", 1, 5000), _topic(3, "C", 1, 9000)]
    adv_quiz = _quiz(202, "advanced")
    db = FakeSession(topics=topics, quiz_sequence=[adv_quiz, adv_quiz, adv_quiz], quiz_fallback=adv_quiz)

    result = assign_learning_path(db, user_id=3, student_level="gioi", document_ids=[1], classroom_id=1)

    assert result["total_assigned"] == 3
    assert len(result["assigned_topics"]) == 3


def test_assign_persists_learner_profile_level():
    topics = [_topic(1, "A", 1, 200)]
    db = FakeSession(topics=topics, quiz_sequence=[None], quiz_fallback=None)

    assign_learning_path(db, user_id=5, student_level="kha", document_ids=[1], classroom_id=2)

    assert db.profile is not None
    assert db.profile.user_id == 5
    assert db.profile.level == "kha"


def test_assign_creates_learning_plan_with_valid_tasks_json():
    topics = [_topic(1, "A", 1, 200)]
    quiz = _quiz(303, "intermediate")
    db = FakeSession(topics=topics, quiz_sequence=[quiz], quiz_fallback=quiz)

    assign_learning_path(db, user_id=6, student_level="trung_binh", document_ids=[1], classroom_id=2)

    assert db.plans
    tasks = db.plans[-1].plan_json.get("tasks")
    assert isinstance(tasks, list)
    assert tasks and {"topic_id", "document_id", "status", "quiz_level"}.issubset(tasks[0].keys())


def test_get_my_path_endpoint_returns_expected_data():
    app = FastAPI()
    @app.middleware("http")
    async def _request_id_middleware(request, call_next):
        request.state.request_id = "test-request-id"
        return await call_next(request)

    app.include_router(router, prefix="/api")

    db = FakeSession()
    db.profile = LearnerProfile(user_id=7, level="trung_binh", mastery_json={})
    db.plans = [
        LearningPlan(
            id=99,
            user_id=7,
            classroom_id=1,
            level="trung_binh",
            plan_json={"tasks": [{"topic_id": 1, "topic_title": "So hoc", "status": "pending"}]},
        )
    ]

    def _override_db():
        return db

    app.dependency_overrides[get_db] = _override_db

    client = TestClient(app)
    resp = client.get("/api/lms/student/7/my-path")
    body = resp.json()

    assert resp.status_code == 200
    assert body["data"]["student_level"] == "trung_binh"
    assert body["data"]["plan"]["plan_id"] == 99
    assert body["data"]["plan"]["tasks"][0]["topic_title"] == "So hoc"
