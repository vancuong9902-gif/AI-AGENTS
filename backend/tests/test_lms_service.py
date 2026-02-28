from app.services.document_pipeline import _candidate_page_coverage, _normalize_pipeline_text
from app.services.lms_service import classify_student_level, score_breakdown, build_recommendations


def test_candidate_page_coverage_uses_total_pages_ratio():
    chunks = [{"meta": {"page": 1}}, {"meta": {"page": 2}}, {"meta": {"page": 4}}]
    cov = _candidate_page_coverage(chunks, total_pages=5)
    assert cov == 0.8


def test_normalize_pipeline_text_repairs_spacing_and_controls():
    src = "La\u0323\u0302p\u00a0 tri\u0300nh\x00 Python"
    out = _normalize_pipeline_text(src)
    assert "\x00" not in out
    assert "Lập" in out
    assert "trình" in out


def test_score_breakdown_and_classification_and_recommendation():
    breakdown = [
        {"type": "mcq", "topic": "hàm", "score_points": 1, "max_points": 1, "bloom_level": "remember"},
        {"type": "mcq", "topic": "hàm", "score_points": 0, "max_points": 1, "bloom_level": "apply"},
        {"type": "essay", "topic": "vòng lặp", "score_points": 2, "max_points": 10},
    ]
    scored = score_breakdown(breakdown)
    assert round(scored["overall"]["percent"], 2) == 25.0
    assert "easy" in scored["by_difficulty"]
    assert "medium" in scored["by_difficulty"] or "hard" in scored["by_difficulty"]

    level = classify_student_level(int(scored["overall"]["percent"]))
    assert level == "yeu"

    recs = build_recommendations(breakdown=scored, document_topics=["hàm", "vòng lặp"])
    assert recs
    assert any("hàm" in r["topic"] or "vòng lặp" in r["topic"] for r in recs)
