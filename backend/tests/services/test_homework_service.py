import pytest
from fastapi import HTTPException

from app.services import homework_service as s


def test_sanitize_rubric_caps_points():
    rb = s._sanitize_rubric([{"criterion": "A", "points": 99}], max_points=5)
    assert rb[0]["points"] <= 5


def test_grade_homework_rejects_when_off(monkeypatch):
    monkeypatch.setattr(s, "settings", type("X", (), {"HOMEWORK_AUTO_GRADE": "off"}))
    with pytest.raises(HTTPException):
        s.grade_homework(db=None, stem="abcdefghijk", answer_text="long enough" * 10, max_points=10, rubric=[], sources=[])
