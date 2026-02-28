from __future__ import annotations

from app.services.lms_service import per_student_bloom_analysis
from app.services.topic_service import extract_exercises_from_topic
from app.services.learning_plan_storage_service import grade_homework_from_plan


def test_extract_exercises_from_topic_llm(monkeypatch):
    monkeypatch.setattr("app.services.topic_service.llm_available", lambda: True)
    monkeypatch.setattr(
        "app.services.topic_service.chat_json",
        lambda **kwargs: [{"question": "Tính đạo hàm của x^2", "answer_hint": "Áp dụng quy tắc lũy thừa"}],
    )
    out = extract_exercises_from_topic("Bài tập: Tính đạo hàm của x^2", "Đạo hàm")
    assert out and out[0]["question"].startswith("Tính đạo hàm")


def test_per_student_bloom_analysis_has_weak_topics():
    data = {
        10: [
            {"by_topic": {"đại số": {"percent": 40, "earned": 2, "total": 5}}},
            {"by_topic": {"hình học": {"percent": 90, "earned": 9, "total": 10}}},
        ]
    }
    out = per_student_bloom_analysis(by_student_breakdowns=data)
    assert out[0]["student_id"] == 10
    assert out[0]["weak_topics"][0]["topic"] == "đại số"


def test_grade_homework_from_plan_returns_hint_and_explanation(monkeypatch):
    class _Q:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return type(
                "Plan",
                (),
                {
                    "id": 1,
                    "plan_json": {
                        "days": [
                            {
                                "day_index": 1,
                                "homework": {
                                    "stem": "Câu tự luận",
                                    "max_points": 10,
                                    "rubric": [],
                                    "sources": [],
                                    "mcq_questions": [
                                        {
                                            "question_id": "d1_orig_1",
                                            "stem": "Câu 1",
                                            "options": ["A", "B", "C", "D"],
                                            "correct_index": 0,
                                            "explanation": "Giải thích mẫu",
                                            "hint": "Gợi ý mẫu",
                                            "related_concept": "Đạo hàm",
                                        }
                                    ],
                                },
                            }
                        ]
                    },
                },
            )()

    class _DB:
        def query(self, *_args, **_kwargs):
            return _Q()

        def add(self, *_args, **_kwargs):
            return None

        def commit(self):
            return None

    monkeypatch.setattr(
        "app.services.learning_plan_storage_service.grade_homework",
        lambda *args, **kwargs: {"score_points": 5, "max_points": 10, "comment": "OK", "rubric_breakdown": []},
    )

    out = grade_homework_from_plan(
        _DB(),
        plan_id=1,
        user_id=9,
        day_index=1,
        answer_text="Bài làm",
        mcq_answers={"d1_orig_1": 0},
    )
    assert out["mcq_breakdown"][0]["explanation"] == "Giải thích mẫu"
    assert out["mcq_breakdown"][0]["hint"] == "Gợi ý mẫu"
