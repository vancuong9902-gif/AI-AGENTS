from __future__ import annotations

from app.services import assessment_service


def _vector_for(text: str) -> list[float]:
    t = (text or "").lower()
    if "excluded" in t:
        return [1.0, 0.0]
    if "semantic duplicate" in t:
        return [0.99, 0.01]
    return [0.0, 1.0]


def test_final_semantic_uniqueness_filters_cosine_over_threshold(monkeypatch):
    def _fake_embed_texts(texts, model=None):
        return [_vector_for(t) for t in texts]

    def _fake_embed_text(text, model=None):
        return _vector_for(text)

    monkeypatch.setattr(assessment_service, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr("app.services.embedding_service.embed_text", _fake_embed_text)

    generated = [
        {"stem": "Semantic duplicate of excluded question"},
        {"stem": "Brand new scenario question"},
    ]
    excluded = ["Excluded source question"]

    filtered, removed, mode = assessment_service._filter_semantic_duplicates(
        generated=generated,
        excluded_stems=excluded,
        threshold=0.85,
    )

    assert mode == "embedding"
    assert removed == 1
    assert len(filtered) == 1

    excluded_vec = _vector_for(excluded[0])
    for q in filtered:
        sim = assessment_service._cosine_similarity(_vector_for(q["stem"]), excluded_vec)
        assert sim <= 0.85


def test_semantic_uniqueness_falls_back_to_string_when_embeddings_unavailable(monkeypatch):
    monkeypatch.setattr(assessment_service, "embed_texts", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("no embeddings")))

    generated = [
        {"stem": "How to solve equation x + 2 = 5?"},
        {"stem": "Completely different geometry question"},
    ]
    excluded = ["solve equation x 2 5"]

    filtered, removed, mode = assessment_service._filter_semantic_duplicates(
        generated=generated,
        excluded_stems=excluded,
        threshold=0.85,
    )

    assert mode == "jaccard"
    assert removed >= 0
    assert len(filtered) >= 1
from typing import Any

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
        rows: list[tuple[str]] = []
        for qid in self._excluded_ids:
            for stem in self._db.excluded_stems_by_assessment.get(int(qid), []):
                rows.append((stem,))
        return rows


class _FakeDB:
    def __init__(self, excluded_stems_by_assessment: dict[int, list[str]]):
        self.excluded_stems_by_assessment = excluded_stems_by_assessment
        self._next_quiz_set_id = 200
        self._next_question_id = 2000

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


def test_final_semantic_uniqueness_with_embeddings(monkeypatch):
    excluded = {31: ["solar panel converts sunlight to electricity"]}
    db = _FakeDB(excluded)

    monkeypatch.setattr(assessment_service, "ensure_user_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        assessment_service,
        "_collect_chunks",
        lambda *args, **kwargs: [{"chunk_id": 1, "document_id": 9, "document_title": "Doc", "text": "clean energy and data systems", "score": 1.0}],
    )
    monkeypatch.setattr(assessment_service, "_quiz_refine_enabled", lambda **kwargs: False)
    monkeypatch.setattr(assessment_service, "_pick_sentences", lambda _text: ["s1", "s2", "s3", "s4"])
    monkeypatch.setattr(assessment_service, "_essay_refine_enabled", lambda **kwargs: False)
    monkeypatch.setattr(assessment_service, "_generate_essay_with_llm", lambda *args, **kwargs: [])
    monkeypatch.setattr(assessment_service, "clean_mcq_questions", lambda mcqs, limit: mcqs[:limit])
    monkeypatch.setattr(assessment_service, "_estimate_minutes_llm", lambda **kwargs: None)

    state = {"calls": 0}

    def _fake_gen(_topic: str, _level: str, question_count: int, *_args, **_kwargs):
        state["calls"] += 1
        if state["calls"] == 1:
            return [
                {
                    "type": "mcq",
                    "stem": "Sunlight is transformed into electric power by solar panels.",
                    "options": ["A", "B", "C", "D"],
                    "correct_index": 0,
                    "explanation": "x",
                    "sources": [{"chunk_id": 1}],
                },
                {
                    "type": "mcq",
                    "stem": "How does database indexing speed up query retrieval?",
                    "options": ["A", "B", "C", "D"],
                    "correct_index": 1,
                    "explanation": "x",
                    "sources": [{"chunk_id": 1}],
                },
            ][:question_count]
        return [
            {
                "type": "mcq",
                "stem": "Which caching strategy reduces backend latency in read-heavy APIs?",
                "options": ["A", "B", "C", "D"],
                "correct_index": 2,
                "explanation": "x",
                "sources": [{"chunk_id": 1}],
            }
        ][:question_count]

    def _fake_embed_texts(texts, model=None):
        out = []
        for t in texts:
            s = str(t).lower()
            if "solar" in s or "sunlight" in s or "electric" in s:
                out.append([1.0, 0.0, 0.0])
            else:
                out.append([0.0, 1.0, 0.0])
        return out

    monkeypatch.setattr(assessment_service, "llm_available", lambda: True)
    monkeypatch.setattr(assessment_service, "_generate_mcq_with_llm", _fake_gen)
    monkeypatch.setattr(assessment_service, "embed_texts", _fake_embed_texts)

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
        topics=[],
        exclude_quiz_ids=[31],
        similarity_threshold=0.75,
    )

    stems = [q["stem"] for q in result["questions"]]
    excluded_embeddings = _fake_embed_texts(excluded[31])
    for stem in stems:
        vec = _fake_embed_texts([stem])[0]
        for ex in excluded_embeddings:
            assert assessment_service._cosine_similarity(vec, ex) <= 0.85