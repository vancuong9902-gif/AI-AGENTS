from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
        if e is lms.StudentAssignment:
            return [
                SimpleNamespace(topic_id=1, status="completed", content_json={"topic_title": "Hàm số"}),
                SimpleNamespace(topic_id=1, status="pending", content_json={"topic_title": "Hàm số"}),
                SimpleNamespace(topic_id=2, status="completed", content_json={"topic_title": "Đạo hàm"}),
            ]
        if e is lms.StudySession:
            return self.db.sessions
        if str(e).endswith("classroom_members.user_id"):
            return [(2,), (3,)]
        if e is lms.Attempt:
            return [
                SimpleNamespace(user_id=2, score_percent=80),
                SimpleNamespace(user_id=3, score_percent=60),
            ]
        return []

    def first(self):
        if self.entity is lms.ClassroomMember:
            return SimpleNamespace(id=1)
        return None


class _DB:
    def __init__(self):
        now = datetime.now(timezone.utc)
        self.sessions = [
            SimpleNamespace(started_at=now - timedelta(days=1), duration_seconds=3600, activity_type="reading"),
            SimpleNamespace(started_at=now - timedelta(days=2), duration_seconds=1800, activity_type="quiz"),
        ]

    def query(self, entity):
        return _Q(self, entity)


def test_progress_tracking_payload_shape():
    req = SimpleNamespace(state=SimpleNamespace(request_id="req-progress"))
    user = SimpleNamespace(id=2, role="student")
    out = lms.get_student_progress(request=req, student_id=2, classroom_id=1, db=_DB(), current_user=user)

    data = out["data"]
    assert data["student_id"] == 2
    assert isinstance(data["topics_progress"], list)
    assert isinstance(data["study_sessions"], list)
    assert "streak_days" in data
    assert "comparison_with_class_avg" in data
