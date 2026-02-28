from app.services.document_pipeline import _candidate_page_coverage, _normalize_pipeline_text
from app.services.lms_service import (
    analyze_topic_weak_points,
    build_personalized_content_plan,
    build_recommendations,
    classify_student_level,
    classify_student_multidim,
    generate_student_evaluation_report,
    generate_class_narrative,
    per_student_bloom_analysis,
    score_breakdown,
)


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
    assert level["level_key"] == "yeu"

    recs = build_recommendations(breakdown=scored, document_topics=["hàm", "vòng lặp"])
    assert recs
    assert any("hàm" in r["topic"] or "vòng lặp" in r["topic"] for r in recs)



def test_generate_class_narrative_no_llm(monkeypatch):
    """Fallback khi LLM không available."""

    monkeypatch.setattr("app.services.lms_service.llm_available", lambda: False)
    result = generate_class_narrative(
        total_students=20,
        level_dist={"gioi": 5, "kha": 8, "trung_binh": 5, "yeu": 2},
        weak_topics=[{"topic": "Đạo hàm"}, {"topic": "Tích phân"}],
        avg_improvement=12.5,
    )
    assert len(result) > 50
    assert "Đạo hàm" in result or "12" in result


def test_analyze_topic_weak_points():
    """Phân tích đúng topic yếu nhất."""

    breakdowns = [
        {"by_topic": {"Đạo hàm": {"percent": 40.0}, "Tích phân": {"percent": 75.0}}},
        {"by_topic": {"Đạo hàm": {"percent": 35.0}, "Tích phân": {"percent": 80.0}}},
    ]
    result = analyze_topic_weak_points(breakdowns)
    assert result[0]["topic"] == "Đạo hàm"
    assert result[0]["avg_pct"] == 37.5


def test_classify_student_multidim_and_recommendations_rules():
    scored = {
        "overall": {"percent": 78.0},
        "by_difficulty": {
            "easy": {"percent": 92.0},
            "medium": {"percent": 55.0},
            "hard": {"percent": 25.0},
        },
        "by_topic": {
            "ham": {"percent": 45.0},
            "vong_lap": {"percent": 80.0},
        },
    }
    profile = classify_student_multidim(
        scored,
        time_spent_sec=500,
        estimated_time_sec=1000,
        prev_attempts=[90.0, 80.0, 70.0],
    )
    assert profile.primary_level == "kha"
    assert profile.knowledge_depth == "surface"
    assert profile.time_efficiency == "fast"
    assert profile.consistency == "variable" or profile.consistency == "declining"
    assert profile.topic_mastery["ham"] == "yeu"

    recs = build_recommendations(breakdown=scored, multidim_profile=profile)
    assert any(r["topic"] == "higher_order_thinking" for r in recs)

def test_generate_student_evaluation_report_fallback(monkeypatch):
    monkeypatch.setattr("app.services.lms_service.llm_available", lambda: False)
    out = generate_student_evaluation_report(
        student_id=100,
        pre_attempt={"overall": {"percent": 40.0}},
        post_attempt={
            "overall": {"percent": 70.0},
            "by_topic": {"đại số": {"percent": 80.0}, "hình học": {"percent": 45.0}},
            "by_difficulty": {"easy": {"percent": 90}, "medium": {"percent": 70}, "hard": {"percent": 40}},
        },
        homework_results=[{"completed": True, "score": 75}],
        db=None,
    )
    assert out["overall_grade"] in {"A", "B", "C", "D", "F"}
    assert out["improvement_delta"] == 30.0
    assert isinstance(out["strengths"], list)
    assert isinstance(out["weaknesses"], list)

def test_score_breakdown_includes_bloom_based_weak_topics():
    breakdown = [
        {"topic": "đại số", "score_points": 0, "max_points": 1, "bloom_level": "remember", "type": "mcq"},
        {"topic": "đại số", "score_points": 0, "max_points": 1, "bloom_level": "understand", "type": "mcq"},
        {"topic": "hình học", "score_points": 1, "max_points": 4, "bloom_level": "evaluate", "type": "essay"},
    ]
    scored = score_breakdown(breakdown)
    assert "weak_topics" in scored
    weak = {r["topic"]: r for r in scored["weak_topics"]}
    assert weak["đại số"]["assignment_type"] == "reading"
    assert weak["hình học"]["assignment_type"] == "essay_case_study"


def test_per_student_bloom_analysis_returns_bloom_and_weak_topics():
    attempts = [
        type("A", (), {
            "user_id": 1,
            "breakdown_json": [
                {"bloom_level": "remember", "topic": "đại số", "is_correct": True},
                {"bloom_level": "apply", "topic": "đại số", "is_correct": False},
                {"bloom_level": "analyze", "topic": "hình học", "is_correct": False},
            ],
        })(),
        type("A", (), {
            "user_id": 2,
            "breakdown_json": [
                {"bloom_level": "understand", "topic": "xác suất", "is_correct": True},
            ],
        })(),
    ]

    out = per_student_bloom_analysis(attempts, {10: "diagnostic_pre"})
    assert len(out) == 2
    student_1 = out[0]
    assert student_1["student_id"] == 1
    assert set(student_1["bloom_accuracy"].keys()) == {"remember", "understand", "apply", "analyze", "evaluate", "create"}
    assert student_1["weak_topics"][0]["topic"] in {"đại số", "hình học"}


def test_build_personalized_content_plan_for_yeu_student():
    plan = build_personalized_content_plan(
        db=None,
        user_id=101,
        quiz_attempt_result={
            "overall": {"percent": 40},
            "by_topic": {"đại số": {"percent": 0}, "hình học": {"percent": 30}, "xác suất": {"percent": 70}},
        },
        document_topics=["đại số", "hình học", "xác suất"],
    )

    assert plan["student_level"] == "yeu"
    assert plan["teacher_alert"] is True
    assert plan["exercise_difficulty_mix"] == {"easy": 100, "medium": 0, "hard": 0}
    assert plan["weak_topics"][0] == "đại số"
    assert plan["content_chunks_to_send"]


def test_build_personalized_content_plan_for_gioi_student():
    plan = build_personalized_content_plan(
        db=None,
        user_id=102,
        quiz_attempt_result={
            "overall": {"percent": 90},
            "by_topic": {"đại số": {"percent": 88}, "hình học": {"percent": 86}},
        },
        document_topics=["đại số", "hình học"],
    )

    assert plan["student_level"] == "gioi"
    assert plan["teacher_alert"] is False
    assert plan["exercise_difficulty_mix"] == {"easy": 0, "medium": 0, "hard": 100}
    assert "nghiên cứu độc lập" in plan["personalized_message"]
