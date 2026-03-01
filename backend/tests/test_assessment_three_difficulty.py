from __future__ import annotations

from typing import Any

from app.services import assessment_service


class _FakeQuery:
    def __init__(self, db: "_FakeDB"):
        self._db = db

    def filter(self, *args: Any, **kwargs: Any):
        return self

    def all(self):
        return []


class _FakeDB:
    def __init__(self):
        self._next_quiz_set_id = 200
        self._next_question_id = 2000

    def query(self, _entity: Any):
        return _FakeQuery(self)

    def add(self, obj: Any):
        if obj.__class__.__name__ == "QuizSet" and getattr(obj, "id", None) is None:
            self._next_quiz_set_id += 1
            obj.id = self._next_quiz_set_id
        if obj.__class__.__name__ == "Question" and getattr(obj, "id", None) is None:
            self._next_question_id += 1
            obj.id = self._next_question_id

    def commit(self):
        return None

    def refresh(self, _obj: Any):
        return None

    def flush(self):
        return None


def _mcq(stem: str, bloom: str) -> dict[str, Any]:
    return {
        "type": "mcq",
        "stem": stem,
        "bloom_level": bloom,
        "options": ["A", "B", "C", "D"],
        "correct_index": 0,
        "explanation": "exp",
        "sources": [{"chunk_id": 1}],
    }


def _essay(stem: str, bloom: str) -> dict[str, Any]:
    return {
        "type": "essay",
        "stem": stem,
        "bloom_level": bloom,
        "max_points": 10,
        "rubric": [{"criterion": "x", "max_points": 10}],
        "sources": [{"chunk_id": 1}],
    }


def _calc_difficulty_plan(questions: list[dict[str, Any]]) -> dict[str, int]:
    out = {"easy": 0, "medium": 0, "hard": 0}
    for q in questions:
        bloom = assessment_service.normalize_bloom_level(q.get("bloom_level"))
        if bloom in {"evaluate", "create"}:
            out["hard"] += 1
        elif bloom in {"remember", "understand"}:
            out["easy"] += 1
        elif bloom in {"apply", "analyze"}:
            out["medium"] += 1
    return out


def test_placement_three_difficulty_and_response_plan(monkeypatch):
    db = _FakeDB()

    monkeypatch.setattr(assessment_service, "ensure_user_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        assessment_service,
        "_collect_chunks",
        lambda *args, **kwargs: [
            {
                "chunk_id": 1,
                "document_id": 9,
                "document_title": "Doc",
                "text": "Python basics, control flow, and project design.",
                "score": 1.0,
            }
        ],
    )
    monkeypatch.setattr(assessment_service, "_pick_sentences", lambda text: ["s1", "s2", "s3", "s4", "s5"])
    monkeypatch.setattr(assessment_service, "_quiz_refine_enabled", lambda **kwargs: False)
    monkeypatch.setattr(assessment_service, "_essay_refine_enabled", lambda **kwargs: False)
    monkeypatch.setattr(assessment_service, "clean_mcq_questions", lambda mcqs, limit: mcqs[:limit])
    monkeypatch.setattr(assessment_service, "_estimate_minutes_llm", lambda **kwargs: None)
    monkeypatch.setattr(assessment_service, "llm_available", lambda: True)

    def _fake_gen_mcq(topic: str, level: str, question_count: int, chunks: list[dict[str, Any]], extra_system_hint: str | None = None):
        hint = str(extra_system_hint or "")
        if "TARGET_DIFFICULTY=EASY" in hint:
            bank = [
                _mcq("E1", "remember"),
                _mcq("E2", "understand"),
                _mcq("E3", "remember"),
                _mcq("E4", "understand"),
            ]
            return bank[:question_count]
        if "TARGET_DIFFICULTY=MEDIUM" in hint:
            bank = [
                _mcq("M1", "apply"),
                _mcq("M2", "analyze"),
                _mcq("M3", "apply"),
                _mcq("M4", "analyze"),
            ]
            return bank[:question_count]
        if "TARGET_DIFFICULTY=HARD" in hint:
            bank = [
                _mcq("HM1", "evaluate"),
                _mcq("HM2", "evaluate"),
                _mcq("HM3", "create"),
            ]
            return bank[:question_count]
        return []

    monkeypatch.setattr(assessment_service, "_generate_mcq_with_llm", _fake_gen_mcq)
    monkeypatch.setattr(
        assessment_service,
        "_generate_essay_with_llm",
        lambda *args, **kwargs: [_essay("H1", "evaluate"), _essay("H2", "create")],
    )

    result = assessment_service.generate_assessment(
        db,
        teacher_id=1,
        classroom_id=1,
        title="Placement Test",
        level="intermediate",
        kind="diagnostic_pre",
        easy_count=4,
        medium_count=4,
        hard_mcq_count=2,
        hard_count=2,
        document_ids=[9],
        topics=[],
    )

    assert len(result["questions"]) == 12

    plan = _calc_difficulty_plan(result["questions"])
    assert plan == {"easy": 4, "medium": 4, "hard": 4}
    assert result["difficulty_plan"] == plan
