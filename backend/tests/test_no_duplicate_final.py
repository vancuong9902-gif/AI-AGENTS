from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from app.models.question import Question
from app.services import assessment_service


class _FakeQuery:
    def __init__(self, db: "_FakeDB", entity: Any):
        self._db = db
        self._entity = entity
        self._excluded_ids: list[int] = []

    def filter(self, *criteria: Any):
        for c in criteria:
            right = getattr(c, "right", None)
            value = getattr(right, "value", None)
            if isinstance(value, (list, tuple, set)):
                self._excluded_ids = [int(x) for x in value]
        return self

    def all(self):
        # support only query(Question.stem).filter(Question.quiz_set_id.in_(...)).all()
        rows: list[tuple[str]] = []
        for qid in self._excluded_ids:
            for stem in self._db.excluded_stems_by_assessment.get(int(qid), []):
                rows.append((stem,))
        return rows


class _FakeDB:
    def __init__(self, excluded_stems_by_assessment: dict[int, list[str]]):
        self.excluded_stems_by_assessment = excluded_stems_by_assessment
        self._next_quiz_set_id = 100
        self._next_question_id = 1000

    def query(self, entity: Any):
        return _FakeQuery(self, entity)

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


def _setup_common_mocks(monkeypatch, *, initial_mcqs: list[dict[str, Any]], refill_mcqs: list[dict[str, Any]]):
    monkeypatch.setattr(assessment_service, "ensure_user_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        assessment_service,
        "_collect_chunks",
        lambda *args, **kwargs: [
            {"chunk_id": 1, "document_id": 9, "document_title": "Doc", "text": "Python basics and syntax.", "score": 1.0}
        ],
    )
    monkeypatch.setattr(assessment_service, "_quiz_refine_enabled", lambda **kwargs: False)
    monkeypatch.setattr(assessment_service, "_pick_sentences", lambda text: ["s1", "s2", "s3", "s4"])
    monkeypatch.setattr(assessment_service, "_essay_refine_enabled", lambda **kwargs: False)
    monkeypatch.setattr(assessment_service, "_generate_essay_with_llm", lambda *args, **kwargs: [])
    monkeypatch.setattr(assessment_service, "clean_mcq_questions", lambda mcqs, limit: mcqs[:limit])
    monkeypatch.setattr(assessment_service, "_estimate_minutes_llm", lambda **kwargs: None)

    state = {"calls": 0}

    def _fake_gen(topic: str, level: str, question_count: int, chunks: list[dict[str, Any]], extra_system_hint: str | None = None):
        state["calls"] += 1
        if extra_system_hint:
            return refill_mcqs[:question_count]
        return initial_mcqs[:question_count]

    monkeypatch.setattr(assessment_service, "llm_available", lambda: True)
    monkeypatch.setattr(assessment_service, "_generate_mcq_with_llm", _fake_gen)
    return state


def test_final_has_zero_duplicates_with_placement(monkeypatch):
    """Bài cuối kỳ không được có câu trùng với bài đầu vào."""
    excluded = {11: ["What is Python programming language?"]}
    db = _FakeDB(excluded)

    initial = [
        {"type": "mcq", "stem": "What is Python programming language?", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "x", "sources": [{"chunk_id": 1}]},
        {"type": "mcq", "stem": "Python uses indentation for blocks.", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "x", "sources": [{"chunk_id": 1}]},
        {"type": "mcq", "stem": "Which loop repeats while condition true?", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "x", "sources": [{"chunk_id": 1}]},
    ]
    refill = [
        {"type": "mcq", "stem": "Choose a real-world use of Python in data automation.", "options": ["A", "B", "C", "D"], "correct_index": 1, "explanation": "x", "sources": [{"chunk_id": 1}]}
    ]
    _setup_common_mocks(monkeypatch, initial_mcqs=initial, refill_mcqs=refill)

    result = assessment_service.generate_assessment(
        db,
        teacher_id=1,
        classroom_id=1,
        title="Final Test",
        level="intermediate",
        kind="diagnostic_post",
        easy_count=3,
        hard_count=0,
        document_ids=[9],
        topics=["python"],
        exclude_quiz_ids=[11],
        similarity_threshold=0.75,
    )

    stems = [q["stem"] for q in result["questions"]]
    for stem in stems:
        ratio = SequenceMatcher(None, stem.lower(), "what is python programming language?".lower()).ratio()
        assert ratio < 0.75


def test_filter_removes_high_similarity_stems(monkeypatch):
    """_is_duplicate_stem() catch đúng câu gần giống."""
    excluded = {21: ["what is python programming language"]}
    db = _FakeDB(excluded)

    initial = [
        {"type": "mcq", "stem": "What is the Python programming language?", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "x", "sources": [{"chunk_id": 1}]},
        {"type": "mcq", "stem": "How does machine learning work?", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "x", "sources": [{"chunk_id": 1}]},
    ]
    refill = [{"type": "mcq", "stem": "New non-overlap question", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "x", "sources": [{"chunk_id": 1}]}]
    _setup_common_mocks(monkeypatch, initial_mcqs=initial, refill_mcqs=refill)

    result = assessment_service.generate_assessment(
        db,
        teacher_id=1,
        classroom_id=1,
        title="Final Test",
        level="intermediate",
        kind="diagnostic_post",
        easy_count=2,
        hard_count=0,
        document_ids=[9],
        topics=["python"],
        exclude_quiz_ids=[21],
        similarity_threshold=0.75,
    )

    assert result["excluded_stems_count"] == 1
    assert result["filtered_duplicates"] >= 1
    assert all("python programming language" not in q["stem"].lower() for q in result["questions"])




def test_no_keyword_overlap_between_placement_and_final():
    """String similarity thấp nhưng keyword overlap cao vẫn phải bị filter."""
    excluded = {"describe practical applications of machine learning models in healthcare data analysis"}
    stem = "How are machine learning models applied in healthcare data analysis in practice?"

    low_similarity = SequenceMatcher(
        None,
        stem.lower(),
        "describe practical applications of machine learning models in healthcare data analysis",
    ).ratio()

    assert low_similarity < 0.95
    assert assessment_service._is_dup(stem, excluded, similarity_threshold=0.95)

def test_deficit_refill_generates_new_questions(monkeypatch):
    """Nếu filter loại 3 câu, hệ thống generate thêm 3 câu mới."""
    excluded = {33: ["alpha", "beta", "gamma"]}
    db = _FakeDB(excluded)

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
    _setup_common_mocks(monkeypatch, initial_mcqs=initial, refill_mcqs=refill)

    result = assessment_service.generate_assessment(
        db,
        teacher_id=1,
        classroom_id=1,
        title="Final Test",
        level="intermediate",
        kind="diagnostic_post",
        easy_count=5,
        hard_count=0,
        document_ids=[9],
        topics=["python"],
        exclude_quiz_ids=[33],
        similarity_threshold=0.75,
    )

    assert result["filtered_duplicates"] == 3
    assert len(result["questions"]) >= 5
