from types import SimpleNamespace

from app.api.routes.assessments import _notify_teacher_when_all_final_submitted


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def distinct(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class _DB:
    def __init__(self):
        self.added = []

    def query(self, *entities):
        d = ",".join(str(x).lower() for x in entities)
        if "classroomassessment" in d and "quizset" in d and "classroom" in d:
            ca = SimpleNamespace(classroom_id=10)
            qs = SimpleNamespace(kind="diagnostic_post")
            c = SimpleNamespace(teacher_id=77)
            return _FakeQuery([(ca, qs, c)])
        if "classroommember.user_id" in d:
            return _FakeQuery([(101,), (102,)])
        if "attempt.user_id" in d:
            return _FakeQuery([(101,), (102,)])
        if "notification.id" in d:
            return _FakeQuery([])
        return _FakeQuery([])

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        return None


def test_notification_trigger_when_all_students_submitted():
    db = _DB()
    _notify_teacher_when_all_final_submitted(db, assessment_id=999)
    assert len(db.added) == 1
    notif = db.added[0]
    assert notif.user_id == 77
    assert notif.type == "class_final_ready"
