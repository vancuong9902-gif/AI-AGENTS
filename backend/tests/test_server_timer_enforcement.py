from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.api.routes import lms


class _FakeQuery:
    def __init__(self, entity, db):
        self.entity = entity
        self.db = db
    def __init__(self, db, entity):
        self.db = db
        self.entity = entity

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        if self.entity is lms.UserSession:
            return self.db.session
        if self.entity is lms.QuizSet:
            return self.db.quiz
        return self.db.allowed


class _FakeDB:
    def __init__(self, *, session, quiz, allowed=True):
        self.session = session
        self.quiz = quiz
        self.allowed = (1,) if allowed else None
        self.committed = False

    def query(self, entity):
        return _FakeQuery(entity, self)

    def add(self, _obj):
        return None

    def commit(self):
        self.committed = True

    def refresh(self, _obj):
        return None


class _Req:
    state = SimpleNamespace(request_id="req-timer")


def test_expired_attempt_gets_locked_and_submit_uses_snapshot(monkeypatch):
    started_at = datetime.now(timezone.utc) - timedelta(seconds=120)
    session = SimpleNamespace(
        id=12,
        user_id=7,
        type="quiz_attempt:99",
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
        answers_snapshot_json=[],
        linked_attempt_record_id=None,
    )
    quiz = SimpleNamespace(id=99, duration_seconds=60, level="intermediate", kind="practice", topic="")
    db = _FakeDB(session=session, quiz=quiz)

    monkeypatch.setattr(lms, "score_breakdown", lambda *_: {"overall": {"percent": 80}, "sections": []})
    monkeypatch.setattr(lms, "classify_student_level", lambda *_: {"level_key": "trung_binh"})
    monkeypatch.setattr(lms, "classify_student_multidim", lambda **_: {"ok": True})
    monkeypatch.setattr(lms, "build_recommendations", lambda **_: [])
    monkeypatch.setattr(lms, "assign_learning_path", lambda *args, **kwargs: {"plan_id": 1})
    monkeypatch.setattr(lms, "_normalize_submit_synced_diagnostic", lambda base, **_: base)
    monkeypatch.setattr(lms, "_normalize_synced_diagnostic", lambda base: base)

    submitted_answers = {}

    def _fake_submit_assessment(_db, assessment_id, user_id, duration_sec, answers):
        submitted_answers["answers"] = answers
        return {
            "attempt_id": 345,
            "breakdown": [],
            "total_score_percent": 80,
            "score_percent": 80,
            "correct_count": 1,
            "total_questions": 1,
            "assessment_kind": "practice",
        }

    monkeypatch.setattr(lms, "submit_assessment", _fake_submit_assessment)

    hb_payload = lms.AttemptHeartbeatIn(answers=[{"question_id": 1, "answer_index": 0}])
    hb_resp = lms.heartbeat_attempt(_Req(), attempt_id=12, payload=hb_payload, db=db)

    assert hb_resp["data"]["locked"] is True
    assert hb_resp["data"]["time_left_seconds"] == 0
    assert session.answers_snapshot_json == []  # already expired => do not overwrite snapshot

    session.answers_snapshot_json = [{"question_id": 1, "answer_index": 2}]
    submit_payload = lms.SubmitAttemptByIdIn(answers=[{"question_id": 1, "answer_index": 0}])
    submit_resp = lms.submit_attempt_by_id(_Req(), attempt_id=12, payload=submit_payload, db=db)

    assert submitted_answers["answers"] == [{"question_id": 1, "answer_index": 2}]
    assert submit_resp["data"]["is_late"] is True
    assert submit_resp["data"]["used_snapshot"] is True
    assert submit_resp["data"]["locked"] is True
    assert session.linked_attempt_record_id == 345
        answers_snapshot_json=[{"question_id": 1, "answer_index": 0}],
    )
    quiz_row = SimpleNamespace(id=5, duration_seconds=60, level="intermediate")
    db = _FakeDB(session_row=session_row, quiz_row=quiz_row, questions=[])

    monkeypatch.setattr(lms, "datetime", _FixedDateTime)

    resp = lms.heartbeat_attempt(
        request=_req(),
        attempt_id=11,
        payload=lms.HeartbeatAttemptIn(answers=[{"question_id": 1, "answer_index": 2}]),
        db=db,
    )

    assert resp["data"]["locked"] is True
    assert session_row.locked_at == _FixedDateTime.fixed_now
    assert session_row.ended_at == _FixedDateTime.fixed_now
    # Snapshot must be frozen once locked.
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
        }

    monkeypatch.setattr(lms, "datetime", _FixedDateTime)
    monkeypatch.setattr(lms, "submit_assessment", _fake_submit_assessment)
    monkeypatch.setattr(lms, "score_breakdown", lambda *_args, **_kwargs: {"overall": {"percent": 80}})
    monkeypatch.setattr(lms, "classify_student_level", lambda *_args, **_kwargs: {"level_key": "kha"})
    monkeypatch.setattr(lms, "classify_student_multidim", lambda **_kwargs: {})
    monkeypatch.setattr(lms, "build_recommendations", lambda **_kwargs: [])
    monkeypatch.setattr(lms, "assign_learning_path", lambda *args, **kwargs: {"plan_id": 1})
    monkeypatch.setattr(lms, "notify_teacher_student_finished", lambda *args, **kwargs: None)
    monkeypatch.setattr(lms, "_publish_mas_event_non_blocking", lambda *args, **kwargs: None)

    resp = lms.submit_attempt_by_id(
        request=_req(),
        attempt_id=22,
        payload=lms.SubmitAttemptByIdIn(answers=payload_answers),
        db=db,
    )

    assert captured["answers"] == snapshot_answers
    assert captured["duration_sec"] == 60  # capped at duration_seconds
    assert resp["data"]["is_late"] is True
    assert resp["data"]["used_snapshot"] is True
    assert db.attempt_row.is_late is True
    assert db.attempt_row.deadline_seconds == 60