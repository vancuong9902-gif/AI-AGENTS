from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import openpyxl

from app.models.attempt import Attempt
from app.models.classroom import Classroom, ClassroomMember
from app.models.classroom_assessment import ClassroomAssessment
from app.models.learner_profile import LearnerProfile
from app.models.quiz_set import QuizSet
from app.models.session import Session as UserSession
from app.models.user import User
from app.services import export_xlsx_service


class FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def join(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def group_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class FakeAttemptQuery(FakeQuery):
    def __init__(self, rows):
        super().__init__(rows)
        self._user_id = None

    def filter(self, *args, **kwargs):
        for expr in args:
            left = getattr(expr, "left", None)
            right = getattr(expr, "right", None)
            if getattr(left, "key", None) == "user_id":
                self._user_id = int(getattr(right, "value", 0) or 0)
        return self

    def all(self):
        if self._user_id is None:
            return list(self._rows)
        return [row for row in self._rows if int(row.user_id) == self._user_id]


class FakeDB:
    def __init__(self):
        self.classroom = Classroom(id=100, teacher_id=999, name="Lop 10A", join_code="JOIN100")
        self.students = [
            User(id=1, email="s1@example.com", full_name="Hoc Sinh 1", role="student"),
            User(id=2, email="s2@example.com", full_name="Hoc Sinh 2", role="student"),
        ]
        self.attempts = [
            Attempt(user_id=1, quiz_set_id=13, score_percent=70, duration_sec=1200, answers_json=[], breakdown_json=[]),
            Attempt(user_id=2, quiz_set_id=13, score_percent=58, duration_sec=900, answers_json=[], breakdown_json=[]),
        ]
        self.profiles = [
            LearnerProfile(user_id=1, level="kha", mastery_json={"topic_mastery": {"Dai so": 80, "Hinh hoc": 72}}),
            LearnerProfile(user_id=2, level="trung_binh", mastery_json={"topic_mastery": {"Dai so": 60}}),
        ]
        now = datetime.now(timezone.utc)
        self.sessions = [
            SimpleNamespace(user_id=1, started_at=now - timedelta(hours=2), ended_at=now - timedelta(hours=1)),
            SimpleNamespace(user_id=2, started_at=now - timedelta(hours=1), ended_at=now),
        ]

    def query(self, *entities):
        if len(entities) == 1 and entities[0] is Classroom:
            return FakeQuery([self.classroom])
        if len(entities) == 1 and entities[0] is User:
            return FakeQuery(self.students)
        if len(entities) == 1 and getattr(entities[0], "class_", None) is ClassroomAssessment:
            return FakeQuery([(13,)])
        if len(entities) == 3 and all(getattr(e, "class_", None) is UserSession for e in entities):
            return FakeQuery(self.sessions)
        if len(entities) == 2 and getattr(entities[0], "class_", None) is Attempt:
            return FakeQuery([(1, 1200), (2, 900)])
        if len(entities) == 1 and entities[0] is LearnerProfile:
            return FakeQuery(self.profiles)
        if len(entities) == 1 and entities[0] is Attempt:
            return FakeAttemptQuery(self.attempts)
        raise AssertionError(f"Unexpected query: {entities}")


def test_export_classroom_gradebook_xlsx_has_expected_sheets_and_headers(monkeypatch):
    db = FakeDB()

    scores = {
        (1, "diagnostic_pre"): 55.0,
        (1, "diagnostic_post"): 80.0,
        (2, "diagnostic_pre"): 40.0,
        (2, "diagnostic_post"): 62.0,
    }

    monkeypatch.setattr(
        export_xlsx_service,
        "_latest_score",
        lambda _db, user_id, kind: scores.get((int(user_id), str(kind))),
    )

    out_path = export_xlsx_service.export_classroom_gradebook_xlsx(db=db, classroom_id=100)
    wb = openpyxl.load_workbook(out_path)

    assert wb.sheetnames == ["Tong hop diem", "Topic mastery", "Thong ke lop"]

    gradebook_headers = [cell.value for cell in wb["Tong hop diem"][1]]
    assert gradebook_headers == [
        "STT",
        "Student ID",
        "Ho ten",
        "Email",
        "Diem dau vao (pre)",
        "Diem cuoi ky (post)",
        "TB bai tap (midterm avg)",
        "Tong gio hoc",
        "Xep loai",
    ]

    topic_headers = [cell.value for cell in wb["Topic mastery"][1]]
    assert topic_headers[:2] == ["Student ID", "Ho ten"]

    stats_headers = [cell.value for cell in wb["Thong ke lop"][1]]
    assert stats_headers == ["Chi so", "Pre", "Post", "Midterm"]
