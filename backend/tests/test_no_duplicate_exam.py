from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from app.services import assessment_service


class _FakeQuery:
    def __init__(self, db: "_FakeDB"):
        self._db = db
        self._excluded_ids: list[int] = []

    def filter(self, *criteria: Any):
        for c in criteria:
            right = getattr(c, "right", None)
            value = getattr(right, "value", None)
            if isinstance(value, (list, tuple, set)):
                self._excluded_ids = [int(x) for x in value]
        return self

    def all(self):
        rows: list[tuple[str]] = []
        for qid in self._excluded_ids:
            for stem in self._db.excluded_stems_by_quiz.get(int(qid), []):
                rows.append((stem,))
        return rows


class _FakeDB:
    def __init__(self, excluded_stems_by_quiz: dict[int, list[str]]):
        self.excluded_stems_by_quiz = excluded_stems_by_quiz
        self._next_quiz_set_id = 100
        self._next_question_id = 1000

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


def _setup_mocks(monkeypatch, *, initial_mcqs: list[dict[str, Any]], refill_mcqs: list[dict[str, Any]]):
    monkeypatch.setattr(assessment_service, "ensure_user_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        assessment_service,
        "_collect_chunks",
        lambda *args, **kwargs: [{"chunk_id": 1, "document_id": 9, "document_title": "Doc", "text": "Python basics and syntax.", "score": 1.0}],
    )
    monkeypatch.setattr(assessment_service, "_quiz_refine_enabled", lambda **kwargs: False)
    monkeypatch.setattr(assessment_service, "_pick_sentences", lambda text: ["s1", "s2", "s3", "s4"])
    monkeypatch.setattr(assessment_service, "_essay_refine_enabled", lambda **kwargs: False)
    monkeypatch.setattr(assessment_service, "_generate_essay_with_llm", lambda *args, **kwargs: [])
    monkeypatch.setattr(assessment_service, "clean_mcq_questions", lambda mcqs, limit: mcqs[:limit])
    monkeypatch.setattr(assessment_service, "_estimate_minutes_llm", lambda **kwargs: None)

    def _fake_gen(topic: str, level: str, question_count: int, chunks: list[dict[str, Any]], extra_system_hint: str | None = None):
        if extra_system_hint:
            return refill_mcqs[:question_count]
        return initial_mcqs[:question_count]

    monkeypatch.setattr(assessment_service, "llm_available", lambda: True)
    monkeypatch.setattr(assessment_service, "_generate_mcq_with_llm", _fake_gen)


def test_generate_final_with_exclusion_has_no_overlap(monkeypatch):
    db = _FakeDB({11: ["What is Python programming language?"]})
    initial = [
        {"type": "mcq", "stem": "What is Python programming language?", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "x", "sources": [{"chunk_id": 1}]},
        {"type": "mcq", "stem": "Python uses indentation for blocks.", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "x", "sources": [{"chunk_id": 1}]},
        {"type": "mcq", "stem": "Which loop repeats while condition true?", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "x", "sources": [{"chunk_id": 1}]},
    ]
    refill = [{"type": "mcq", "stem": "Choose a real-world use of Python in data automation.", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "x", "sources": [{"chunk_id": 1}]}]
    _setup_mocks(monkeypatch, initial_mcqs=initial, refill_mcqs=refill)

    result = assessment_service.generate_assessment(
        db,
        teacher_id=1,
        classroom_id=1,
        title="Final Test",
        level="intermediate",
        easy_count=3,
        hard_count=0,
        document_ids=[9],
        topics=["python"],
        kind="diagnostic_post",
        exclude_quiz_ids=[11],
        similarity_threshold=0.75,
    )

    for stem in [q["stem"] for q in result["questions"]]:
        assert SequenceMatcher(None, stem.lower(), "what is python programming language?").ratio() < 0.75


def test_is_dup_true_for_same_stem_ignoring_case():
    assert assessment_service._is_dup(
        "What is Python programming?",
        {"what is python programming?"},
        0.75,
    ) is True


def test_is_dup_false_for_different_stem():
    assert assessment_service._is_dup(
        "How does ML work?",
        {"what is python programming?"},
        0.75,
    ) is False


def test_refill_after_filter_keeps_target_count(monkeypatch):
    db = _FakeDB({33: ["alpha", "beta", "gamma"]})
    initial = [
        {"type": "mcq", "stem": "alpha", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "x", "sources": [{"chunk_id": 1}]},
        {"type": "mcq", "stem": "beta", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "x", "sources": [{"chunk_id": 1}]},
        {"type": "mcq", "stem": "gamma", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "x", "sources": [{"chunk_id": 1}]},
        {"type": "mcq", "stem": "delta unique", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "x", "sources": [{"chunk_id": 1}]},
        {"type": "mcq", "stem": "epsilon unique", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "x", "sources": [{"chunk_id": 1}]},
    ]
    refill = [
        {"type": "mcq", "stem": "zeta unique", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "x", "sources": [{"chunk_id": 1}]},
        {"type": "mcq", "stem": "eta unique", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "x", "sources": [{"chunk_id": 1}]},
        {"type": "mcq", "stem": "theta unique", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "x", "sources": [{"chunk_id": 1}]},
    ]
    _setup_mocks(monkeypatch, initial_mcqs=initial, refill_mcqs=refill)

    result = assessment_service.generate_assessment(
        db,
        teacher_id=1,
        classroom_id=1,
        title="Final Test",
        level="intermediate",
        easy_count=5,
        hard_count=0,
        document_ids=[9],
        topics=["python"],
        kind="diagnostic_post",
        exclude_quiz_ids=[33],
        similarity_threshold=0.75,
    )

    assert len(result["questions"]) >= 5
