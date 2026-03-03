from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.api.routes import lms


class _Q:
    def __init__(self, db, entity):
        self.db = db
        self.entity = entity

    def filter(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        e = self.entity
        if e is lms.Attempt:
            return self.db.attempts
        if str(e).endswith("classroom_members.user_id"):
            return [(2,)]
        return []

    def first(self):
        e = self.entity
        if e is lms.Classroom:
            return SimpleNamespace(id=1, teacher_id=1)
        if e is lms.ClassroomMember:
            return SimpleNamespace(id=1, classroom_id=1, user_id=2)
        if e is lms.QuizSet:
            return self.db.quiz_kind_lookup.pop(0) if self.db.quiz_kind_lookup else None
        if e is lms.User:
            return SimpleNamespace(id=2, full_name="HS A")
        return None

    def count(self):
        return 2

    def scalar(self):
        return 7200


class _DB:
    def __init__(self):
        self.attempts = [
            SimpleNamespace(quiz_set_id=11, score_percent=55, breakdown_json=[], created_at=datetime.now(timezone.utc)),
            SimpleNamespace(quiz_set_id=12, score_percent=78, breakdown_json=[{"topic": "Hàm số", "score_points": 3, "max_points": 10}], created_at=datetime.now(timezone.utc)),
        ]
        self.quiz_kind_lookup = [
            SimpleNamespace(kind="diagnostic_pre"),
            SimpleNamespace(kind="diagnostic_post"),
        ]

    def query(self, entity):
        return _Q(self, entity)

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = 1

    def commit(self):
        return None

    def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = 1


def test_student_evaluation_endpoint_returns_payload(monkeypatch):
    monkeypatch.setattr(lms, "chat_text", lambda *a, **k: "Đánh giá tổng quát học viên.")
    req = SimpleNamespace(state=SimpleNamespace(request_id="req-eval"))
    user = SimpleNamespace(id=1, role="teacher")

    out = lms.generate_student_evaluation(
        request=req,
        student_id=2,
        classroom_id=1,
        db=_DB(),
        current_user=user,
    )

    assert out["data"]["student_id"] == 2
    assert out["data"]["classroom_id"] == 1
    assert out["data"]["evaluation"]
    assert out["data"]["grade"] in {"Xuất sắc", "Giỏi", "Khá", "Trung bình", "Yếu"}
