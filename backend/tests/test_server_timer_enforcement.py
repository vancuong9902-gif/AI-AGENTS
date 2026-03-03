from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.api.routes import lms


class _FakeQuery:
    def __init__(self, db, entity):
        self.db = db
        self.entity = entity

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        e = self.entity
        if e is lms.UserSession:
            return self.db.session_row
        if e is lms.QuizSet:
            return self.db.quiz_row
        if e is lms.Attempt:
            return self.db.attempt_row
        if str(e).endswith("classroom_assessments.id"):
            return (1,)
        return None

    def all(self):
        if self.entity is lms.Question:
            return self.db.questions
        return []


class _FakeDB:
    def __init__(self, *, session_row, quiz_row, questions):
        self.session_row = session_row
        self.quiz_row = quiz_row
        self.questions = questions
        self.attempt_row = SimpleNamespace(id=777, is_late=False, deadline_seconds=0)

    def query(self, entity):
        return _FakeQuery(self, entity)

    def add(self, _):
        return None

    def commit(self):
        return None

    def refresh(self, _):
        return None


class _FixedDateTime(datetime):
    fixed_now = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        if tz is not None:
            return cls.fixed_now.astimezone(tz)
        return cls.fixed_now


def _req():
    return SimpleNamespace(state=SimpleNamespace(request_id="req-timer"))


def test_heartbeat_locks_attempt_after_deadline(monkeypatch):
    started_at = _FixedDateTime.fixed_now - timedelta(seconds=61)
    session_row = SimpleNamespace(
        id=11,
        user_id=9,
        type="quiz_attempt:5",
        started_at=started_at,
        ended_at=None,
        locked_at=None,
        last_heartbeat_at=None,
        answers_snapshot_json=[{"question_id": 1, "answer_index": 0}],
        linked_attempt_record_id=None,
    )
    quiz_row = SimpleNamespace(id=5, duration_seconds=60, level="intermediate", kind="practice", topic="")
    db = _FakeDB(session_row=session_row, quiz_row=quiz_row, questions=[])

    monkeypatch.setattr(lms, "datetime", _FixedDateTime)

    resp = lms.heartbeat_attempt(
        request=_req(),
        attempt_id=11,
        payload=lms.AttemptHeartbeatIn(answers=[{"question_id": 1, "answer_index": 2}]),
        db=db,
    )

    assert resp["data"]["locked"] is True
    assert session_row.locked_at == _FixedDateTime.fixed_now
    assert session_row.ended_at == _FixedDateTime.fixed_now
    assert session_row.answers_snapshot_json == [{"question_id": 1, "answer_index": 0}]


def test_submit_uses_snapshot_when_late_and_locked(monkeypatch):
    started_at = _FixedDateTime.fixed_now - timedelta(seconds=140)
    snapshot_answers = [{"question_id": 101, "answer_index": 3, "answer_text": None}]
    payload_answers = [{"question_id": 101, "answer_index": 1, "answer_text": None}]

    session_row = SimpleNamespace(
        id=22,
        user_id=9,
        type="quiz_attempt:5",
        started_at=started_at,
        ended_at=None,
        locked_at=_FixedDateTime.fixed_now - timedelta(seconds=5),
        last_heartbeat_at=None,
        answers_snapshot_json=snapshot_answers,
        linked_attempt_record_id=None,
    )
    quiz_row = SimpleNamespace(id=5, duration_seconds=60, level="intermediate", kind="midterm", topic="")
    questions = [SimpleNamespace(id=101, order_no=1)]
    db = _FakeDB(session_row=session_row, quiz_row=quiz_row, questions=questions)

    captured = {}

    def _fake_submit_assessment(db, *, assessment_id, user_id, duration_sec, answers):
        captured["duration_sec"] = duration_sec
        captured["answers"] = answers
        return {
            "attempt_id": 777,
            "breakdown": [],
            "total_score_percent": 80,
            "score_percent": 80,
            "assessment_kind": "midterm",
        }

    monkeypatch.setattr(lms, "datetime", _FixedDateTime)
    monkeypatch.setattr(lms, "submit_assessment", _fake_submit_assessment)
    monkeypatch.setattr(lms, "score_breakdown", lambda *_args, **_kwargs: {"overall": {"percent": 80}, "weak_topics": []})
    monkeypatch.setattr(lms, "classify_student_level", lambda *_args, **_kwargs: {"level_key": "kha", "label": "Khá"})
    monkeypatch.setattr(lms, "classify_student_multidim", lambda **_kwargs: {})
    monkeypatch.setattr(lms, "build_recommendations", lambda **_kwargs: [])
    monkeypatch.setattr(lms, "assign_learning_path", lambda *args, **kwargs: {"plan_id": 1})
    monkeypatch.setattr(lms, "notify_teacher_student_finished", lambda *args, **kwargs: None)
    monkeypatch.setattr(lms, "_publish_mas_event_non_blocking", lambda *args, **kwargs: None)
    monkeypatch.setattr(lms, "_normalize_submit_synced_diagnostic", lambda base, **_: base)

    resp = lms.submit_attempt_by_id(
        request=_req(),
        attempt_id=22,
        payload=lms.SubmitAttemptByIdIn(answers=payload_answers),
        db=db,
    )

    assert captured["answers"] == snapshot_answers
    assert captured["duration_sec"] == 60
    assert resp["data"]["is_late"] is True
    assert resp["data"]["used_snapshot"] is True
    assert db.attempt_row.is_late is True
    assert db.attempt_row.deadline_seconds == 60


def test_lms_submit_attempt_ignores_client_duration(monkeypatch):
    started_at = _FixedDateTime.fixed_now - timedelta(seconds=120)

    class _FakeQuerySubmit(_FakeQuery):
        def __init__(self, db, entity):
            super().__init__(db, entity)

        def limit(self, *args, **kwargs):
            return self

    class _FakeDBSubmit(_FakeDB):
        def query(self, entity):
            return _FakeQuerySubmit(self, entity)

    session_row = SimpleNamespace(
        id=33,
        user_id=9,
        type="quiz_attempt:5",
        started_at=started_at,
        ended_at=None,
        locked_at=None,
        last_heartbeat_at=None,
        answers_snapshot_json=[{"question_id": 101, "answer_index": 2}],
        linked_attempt_record_id=None,
    )
    quiz_row = SimpleNamespace(id=5, duration_seconds=60, level="intermediate", kind="midterm", topic="A")
    db = _FakeDBSubmit(session_row=session_row, quiz_row=quiz_row, questions=[])

    captured = {}

    def _fake_submit_assessment(_db, *, assessment_id, user_id, duration_sec, answers):
        captured["duration_sec"] = duration_sec
        captured["answers"] = answers
        return {"attempt_id": 1, "breakdown": [], "assessment_kind": "midterm", "score_percent": 70}

    monkeypatch.setattr(lms, "datetime", _FixedDateTime)
    monkeypatch.setattr(lms, "submit_assessment", _fake_submit_assessment)
    monkeypatch.setattr(lms, "score_breakdown", lambda *_a, **_k: {"overall": {"percent": 70}, "weak_topics": []})
    monkeypatch.setattr(lms, "classify_student_level", lambda *_a, **_k: {"level_key": "kha"})
    monkeypatch.setattr(lms, "classify_student_multidim", lambda **_k: {})
    monkeypatch.setattr(lms, "build_recommendations", lambda **_k: [])
    monkeypatch.setattr(lms, "persist_multidim_profile", lambda *_a, **_k: {"profile": {}, "key": "k"})
    monkeypatch.setattr(lms, "assign_topic_materials", lambda *_a, **_k: [])
    monkeypatch.setattr(lms, "_normalize_submit_synced_diagnostic", lambda base, **_: base)
    monkeypatch.setattr(lms, "_normalize_synced_diagnostic", lambda base: base)

    resp = lms.lms_submit_attempt(
        request=_req(),
        assessment_id=5,
        payload=lms.SubmitAttemptIn(user_id=9, duration_sec=5, answers=[{"question_id": 101, "answer_index": 1}]),
        db=db,
    )

    assert captured["duration_sec"] == 60
    assert resp["data"]["time_spent_seconds"] == 120
    assert resp["data"]["timed_out"] is True
    assert resp["data"]["late_submission"] is True
