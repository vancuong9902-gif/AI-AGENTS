from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import sys
import types

if "jinja2" not in sys.modules:
    m = types.ModuleType("jinja2")
    m.Environment = lambda *args, **kwargs: None
    m.FileSystemLoader = lambda *args, **kwargs: None
    m.select_autoescape = lambda *args, **kwargs: None
    sys.modules["jinja2"] = m

from app.api.routes import lms
from app.models.attempt import Attempt
from app.models.classroom_assessment import ClassroomAssessment
from app.models.question import Question
from app.models.quiz_set import QuizSet
from app.models.quiz_session import QuizSession
from app.models.session import Session as UserSession
from app.services import assessment_service


class _FakeQuery:
    def __init__(self, data):
        self._data = list(data)
    def __init__(self, first_value=None, all_value=None):
        self._first_value = first_value
        self._all_value = all_value if all_value is not None else []

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def first(self):
        return self._data[0] if self._data else None

    def all(self):
        return list(self._data)


class _FakeDB:
    def __init__(self, mapping):
        self.mapping = mapping
        self.added = []

    def query(self, entity, *_args, **_kwargs):
        return _FakeQuery(self.mapping.get(entity, []))

    def add(self, obj):
        return self._first_value

    def all(self):
        return self._all_value


class _FakeDB:
    def __init__(self, quiz_set, questions, session):
        self.quiz_set = quiz_set
        self.questions = questions
        self.session = session
        self.added = []

    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "QuizSet":
            return _FakeQuery(first_value=self.quiz_set)
        if name == "Question":
            return _FakeQuery(all_value=self.questions)
        if name == "QuizSession":
            return _FakeQuery(first_value=self.session)
        if name == "ClassroomAssessment":
            return _FakeQuery(first_value=None)
        raise AssertionError(f"Unexpected model queried: {name}")

    def add(self, obj):
        if getattr(obj, "id", None) is None and obj.__class__.__name__ == "Attempt":
            obj.id = 999
        self.added.append(obj)

    def commit(self):
        return None

    def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = 999


def test_submit_assessment_breakdown_contains_bloom_level(monkeypatch):
    now = datetime.now(timezone.utc)
    quiz = SimpleNamespace(
        id=11,
        kind="assessment",
        topic="Đại số",
        duration_seconds=1800,
        submitted_at=None,
        document_ids_json=None,
    )
    session = SimpleNamespace(
        quiz_set_id=11,
        user_id=7,
        started_at=now - timedelta(minutes=8),
        time_limit_seconds=1800,
        submitted_at=None,
    )
    questions = [
        SimpleNamespace(
            id=101,
            order_no=1,
            type="mcq",
            stem="2+2=?",
            correct_index=1,
            explanation="Vì 2+2=4",
            sources=[{"chunk_id": 7}],
            bloom_level="remember",
            options=["3", "4", "5"],
            max_points=1,
            rubric=[],
        ),
        SimpleNamespace(
            id=102,
            order_no=2,
            type="essay",
            stem="Giải thích định nghĩa hàm số",
            correct_index=0,
            explanation="Nêu đúng định nghĩa",
            sources=[{"chunk_id": 8}],
            bloom_level="analyze",
            options=[],
            max_points=10,
            rubric=[],
        ),
    ]

    db = _FakeDB(
        {
            QuizSet: [quiz],
            Question: questions,
            QuizSession: [session],
            ClassroomAssessment: [],
        }
    )

    monkeypatch.setattr(assessment_service, "ensure_user_exists", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(assessment_service, "retrieve_and_log", lambda *_args, **_kwargs: {"chunks": []})
    monkeypatch.setattr(assessment_service, "llm_available", lambda: False)
    monkeypatch.setattr(assessment_service, "_essay_autograde_enabled", lambda: False)
    monkeypatch.setattr(assessment_service, "_build_answer_review", lambda **_kwargs: [])

    out = assessment_service.submit_assessment(
        db,
        assessment_id=11,
        user_id=7,
        duration_sec=480,
        answers=[
            {"question_id": 101, "answer_index": 1},
            {"question_id": 102, "answer_text": "Hàm số là ánh xạ..."},
        ],
    )

    breakdown = out["breakdown"]
    assert breakdown[0]["bloom_level"] == "remember"
    assert breakdown[1]["bloom_level"] == "analyze"


def test_get_attempt_result_includes_difficulty_and_summary_keys():
    started_at = datetime.now(timezone.utc) - timedelta(minutes=15)
    attempt_created = datetime.now(timezone.utc) - timedelta(minutes=2)

    session = SimpleNamespace(id=55, user_id=7, type="quiz_attempt:11", started_at=started_at)
    quiz = SimpleNamespace(id=11, kind="assessment", topic="Hàm số", duration_seconds=600)
    attempt = SimpleNamespace(
        id=999,
        user_id=7,
        quiz_set_id=11,
        score_percent=75,
        duration_sec=620,
        is_late=True,
        created_at=attempt_created,
        breakdown_json=[
            {
                "question_id": 101,
                "order_no": 1,
                "type": "mcq",
                "topic": "đại số",
                "bloom_level": "apply",
                "chosen": 0,
                "correct": 1,
                "is_correct": False,
                "score_points": 0,
                "max_points": 1,
                "sources": [{"chunk_id": 7}],
            },
        ],
    )
    questions = [
        SimpleNamespace(
            id=101,
            order_no=1,
            stem="f(x)=x^2, f(2)=?",
            type="mcq",
            bloom_level="apply",
            options=["2", "4", "8"],
            correct_index=1,
            explanation="Thay x=2 vào hàm số",
            sources=[{"chunk_id": 7}],
        )
    ]

    db = _FakeDB(
        {
            UserSession: [session],
            QuizSet: [quiz],
            Attempt: [attempt],
            Question: questions,
        }
    )
    req = SimpleNamespace(state=SimpleNamespace(request_id="rid-1"))

    out = lms.get_attempt_result(req, 55, db)
    detail = out["data"]["result_detail"]

    assert detail["questions_detail"][0]["difficulty"]
    assert set(detail["summary"]["by_difficulty"].keys()) >= {"easy", "medium", "hard"}
        return None


def test_submit_assessment_includes_detail_fields_and_summary(monkeypatch):
    now = datetime.now(timezone.utc)
    quiz_set = SimpleNamespace(
        id=10,
        kind="assessment",
        topic="Đại số",
        duration_seconds=900,
        submitted_at=None,
        document_ids_json=None,
    )
    question = SimpleNamespace(
        id=101,
        quiz_set_id=10,
        order_no=1,
        type="mcq",
        stem="2 + 2 bằng mấy?",
        options=["3", "4", "5", "6"],
        correct_index=1,
        explanation="Vì 2 + 2 = 4 theo phép cộng cơ bản.",
        sources=[{"chunk_id": 1}],
        bloom_level="remember",
        max_points=1,
        rubric=None,
    )
    session = SimpleNamespace(
        quiz_set_id=10,
        user_id=7,
        started_at=now - timedelta(minutes=3),
        time_limit_seconds=900,
        submitted_at=None,
    )
    db = _FakeDB(quiz_set=quiz_set, questions=[question], session=session)

    monkeypatch.setattr(assessment_service, "ensure_user_exists", lambda *args, **kwargs: None)

    result = assessment_service.submit_assessment(
        db,
        assessment_id=10,
        user_id=7,
        answers=[{"question_id": 101, "answer_index": 1}],
    )

    row = result["breakdown"][0]
    assert row["stem"] == "2 + 2 bằng mấy?"
    assert row["options"] == ["3", "4", "5", "6"]
    assert row["difficulty"] == "easy"
    assert row["correct_answer_text"] == "4"
    assert row["student_answer_text"] == "4"

    summary = result["summary"]
    assert "by_topic" in summary
    assert "by_difficulty" in summary
    assert set(summary["by_difficulty"].keys()) == {"easy", "medium", "hard"}

    topic_bucket = summary["by_topic"][next(iter(summary["by_topic"]))]
    assert {"earned", "total", "percent"}.issubset(topic_bucket.keys())