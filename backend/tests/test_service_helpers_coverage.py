from __future__ import annotations

import hashlib
import sys
import types

if "tenacity" not in sys.modules:
    tenacity = types.ModuleType("tenacity")

    def _identity(*args, **kwargs):
        def _wrap(fn):
            return fn
        return _wrap

    tenacity.before_sleep_log = lambda *args, **kwargs: None
    tenacity.retry = _identity
    tenacity.retry_if_exception_type = lambda *args, **kwargs: None
    tenacity.stop_after_attempt = lambda *args, **kwargs: None
    tenacity.wait_exponential = lambda *args, **kwargs: None
    sys.modules["tenacity"] = tenacity

from app.services import agent_service, analytics_service, assessment_service


def test_assessment_coerce_document_ids_normalizes_and_deduplicates():
    assert assessment_service._coerce_document_ids(None) == []
    assert assessment_service._coerce_document_ids('["1", 2, "x", 2, -1, 0]') == [1, 2]
    assert assessment_service._coerce_document_ids("7") == [7]
    assert assessment_service._coerce_document_ids({"id": 9}) == []


def test_assessment_fallback_explanation_handles_variants_and_truncates_stem():
    stem = "A" * 200
    out_with_choice = assessment_service._fallback_mcq_explanation(
        stem=stem,
        correct_text="Đáp án đúng",
        chosen_text="Đáp án sai",
    )
    assert "Bạn đã chọn 'Đáp án sai'" in out_with_choice
    assert "đáp án đúng là 'Đáp án đúng'" in out_with_choice
    assert "..." in out_with_choice

    out_without_choice = assessment_service._fallback_mcq_explanation(
        stem="",
        correct_text="Đúng",
        chosen_text=None,
    )
    assert "Đáp án đúng là 'Đúng'" in out_without_choice
    assert "câu hỏi này" in out_without_choice


def test_assessment_dedup_normalization_and_similarity_detection():
    normalized = assessment_service._normalize_stem_for_dedup("  Python!!! là gì???  ")
    assert normalized == "python là gì"

    excluded = {"python la gi", "đạo hàm là gì"}
    assert assessment_service._is_dup("Python là gì?", excluded_stems=excluded, similarity_threshold=0.6)
    assert not assessment_service._is_dup("Khái niệm ma trận", excluded_stems=excluded, similarity_threshold=0.9)


def test_analytics_weight_normalization_and_time_quality_ranges():
    normalized = analytics_service._normalize_weights({
        "w1_knowledge": 3,
        "w2_improvement": 1,
        "w3_engagement": -5,
        "w4_retention": 0,
    })
    assert round(sum(normalized.values()), 8) == 1.0
    assert normalized["w1_knowledge"] == 0.75
    assert normalized["w3_engagement"] == 0.0

    fallback = analytics_service._normalize_weights({"x": -1})
    assert fallback == {
        "w1_knowledge": 0.25,
        "w2_improvement": 0.25,
        "w3_engagement": 0.25,
        "w4_retention": 0.25,
    }

    assert analytics_service._time_quality(0) == 0.0
    assert analytics_service._time_quality(15) == 0.5
    assert analytics_service._time_quality(30) == 1.0
    assert analytics_service._time_quality(120) < 1.0
    assert analytics_service._time_quality(240) == 0.2


def test_analytics_parse_mastery_and_compute_knowledge_fallbacks():
    mj = {
        "topic_mastery": {
            "doc9:t1": 0.7,
            "doc9:t2": "0.5",
            "doc8:t3": 0.9,
            "__global__": 1.0,
            "bad": "x",
        }
    }

    parsed = analytics_service._parse_topic_mastery(mj, document_id=9)
    assert parsed == {"doc9:t1": 0.7, "doc9:t2": 0.5}

    knowledge_doc9 = analytics_service.compute_knowledge(mj, document_id=9)
    assert knowledge_doc9 == 0.6

    knowledge_fallback = analytics_service.compute_knowledge({"__last_exam_score_percent__": 0.88}, document_id=1)
    assert knowledge_fallback == 0.88


def test_agent_summary_and_fingerprint_helpers(monkeypatch):
    short = agent_service._short_doc_summary(" ")
    assert short == ""

    long_text = "x" * 900
    summarized = agent_service._short_doc_summary(long_text)
    assert len(summarized) == 800
    assert summarized.endswith("…")

    monkeypatch.setattr(agent_service, "llm_available", lambda: False)
    assert agent_service._llm_doc_summary("A" * 50, title="Doc") == "A" * 50

    monkeypatch.setattr(agent_service, "llm_available", lambda: True)
    monkeypatch.setattr(agent_service, "chat_json", lambda **kwargs: {"bullets": ["ý 1", "ý 2"]})
    llm_summary = agent_service._llm_doc_summary("Nội dung", title="Doc")
    assert llm_summary == "- ý 1\n- ý 2"

    a = agent_service._stem_fingerprint("Python là gì?")
    b = agent_service._stem_fingerprint("  python   là gì   ")
    assert a == b
    assert a == hashlib.sha256("python là gì".encode("utf-8")).hexdigest()
