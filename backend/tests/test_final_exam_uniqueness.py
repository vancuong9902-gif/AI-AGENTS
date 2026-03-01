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
