from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.api.routes import lms


class _FakeQuery:
    def __init__(self, entity, db):
        self.entity = entity
        self.db = db

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
