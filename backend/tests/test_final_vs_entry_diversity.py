from __future__ import annotations

from typing import Any

from app.services import assessment_service


class _FakeQuery:
    def __init__(self, db: "_FakeDB"):
        self._db = db
        self._mode = ""
        self._quiz_ids: list[int] = []
        self._question_ids: list[int] = []

    def filter(self, *criteria: Any):
        for c in criteria:
            right = getattr(c, "right", None)
            value = getattr(right, "value", None)
            if isinstance(value, (list, tuple, set)):
                vals = [int(x) for x in value]
                if self._mode == "stems_by_quiz":
                    self._quiz_ids = vals
                elif self._mode == "stems_by_qid":
                    self._question_ids = vals
        return self

    def order_by(self, *_args: Any, **_kwargs: Any):
        return self

    def limit(self, *_args: Any, **_kwargs: Any):
        return self

    def all(self):
        if self._mode == "stems_by_quiz":
            rows: list[tuple[str]] = []
            for qid in self._quiz_ids:
                for stem in self._db.excluded_stems_by_quiz.get(int(qid), []):
                    rows.append((stem,))
            return rows
        if self._mode == "stems_by_qid":
            rows: list[tuple[str]] = []
            for qid in self._question_ids:
                stem = self._db.excluded_stems_by_question.get(int(qid))
                if stem:
                    rows.append((stem,))
            return rows
        return []

    def first(self):
        return None


class _FakeDB:
    def __init__(self, excluded_stems_by_quiz: dict[int, list[str]], excluded_stems_by_question: dict[int, str]):
        self.excluded_stems_by_quiz = excluded_stems_by_quiz
        self.excluded_stems_by_question = excluded_stems_by_question
        self._next_quiz_set_id = 100
        self._next_question_id = 1000

    def query(self, entity: Any):
        q = _FakeQuery(self)
        name = getattr(entity, "name", "")
        key = str(name)
        if key == "stem":
            q._mode = "stems_by_quiz"
        return q

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


def test_final_exam_has_no_exact_overlap_and_higher_bloom(monkeypatch):
    entry_quiz_id = 11
    entry_stems = [f"entry stem {i}" for i in range(30)]
    excluded_qids = {i + 1: s for i, s in enumerate(entry_stems)}
    db = _FakeDB({entry_quiz_id: entry_stems}, excluded_qids)

    monkeypatch.setattr(assessment_service, "ensure_user_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        assessment_service,
        "_collect_chunks",
        lambda *args, **kwargs: [{"chunk_id": 1, "document_id": 9, "document_title": "Doc", "text": "Python practical scenario and analysis.", "score": 1.0}],
    )
    monkeypatch.setattr(assessment_service, "_quiz_refine_enabled", lambda **kwargs: False)
    monkeypatch.setattr(assessment_service, "_pick_sentences", lambda text: ["s1", "s2", "s3", "s4"])
    monkeypatch.setattr(assessment_service, "_essay_refine_enabled", lambda **kwargs: False)
    monkeypatch.setattr(assessment_service, "_generate_essay_with_llm", lambda *args, **kwargs: [])
    monkeypatch.setattr(assessment_service, "clean_mcq_questions", lambda mcqs, limit: mcqs[:limit])
    monkeypatch.setattr(assessment_service, "_estimate_minutes_llm", lambda **kwargs: None)
    monkeypatch.setattr(assessment_service, "embed_texts", lambda texts: [[0.1, 0.2, 0.3] for _ in texts])

    def _fake_gen(_topic: str, _level: str, question_count: int, _chunks: list[dict[str, Any]], extra_system_hint: str | None = None):
        out = []
        for i in range(question_count):
            out.append(
                {
                    "type": "mcq",
                    "bloom_level": "apply" if i % 2 == 0 else "analyze",
                    "stem": f"final scenario question {i}",
                    "options": ["A", "B", "C", "D"],
                    "correct_index": 0,
                    "explanation": "x",
                    "sources": [{"chunk_id": 1}],
                }
            )
        return out

    monkeypatch.setattr(assessment_service, "llm_available", lambda: True)
    monkeypatch.setattr(assessment_service, "_generate_mcq_with_llm", _fake_gen)

    result = assessment_service.generate_assessment(
        db,
        teacher_id=1,
        classroom_id=1,
        title="Final Exam",
        level="intermediate",
        kind="diagnostic_post",
        easy_count=0,
        medium_count=30,
        hard_count=0,
        document_ids=[9],
        topics=["python"],
        exclude_quiz_ids=[entry_quiz_id],
    )

    final_stems = [q["stem"] for q in result["questions"]]
    assert not (set(final_stems) & set(entry_stems))

    high_bloom = [q for q in result["questions"] if str(q.get("bloom_level")) in {"apply", "analyze", "evaluate", "create"}]
    assert (len(high_bloom) / max(1, len(result["questions"]))) > 0.5
