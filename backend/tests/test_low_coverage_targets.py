from __future__ import annotations

import sys
import types

import pytest
from fastapi import HTTPException

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

from app.services import agent_service, analytics_service, assessment_service, text_quality, tutor_service


def test_text_quality_report_and_filter_cover_garbled_paths():
    clean = "Đây là đoạn văn bản tiếng Việt rõ ràng có đủ nội dung để đánh giá chất lượng tốt."
    garbled = "t r ì n h b à y � � 1 2 3 { } [ ] ; :"

    clean_score = text_quality.quality_score(clean)
    garbled_report = text_quality.quality_report(garbled)

    assert clean_score > 0.3
    assert garbled_report["score"] < 0.3
    assert "replacement_char" in garbled_report["reasons"]

    good, bad = text_quality.filter_chunks_by_quality(
        [{"chunk_id": 1, "text": clean}, {"chunk_id": 2, "text": garbled}],
        min_score=0.3,
    )
    assert [c["chunk_id"] for c in good] == [1]
    assert bad[0]["chunk_id"] == 2
    assert "_quality" in bad[0]


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("entry_test", 9),
        ("retention_check", 3),
        ("final_exam", 8),
    ],
)
def test_agent_expected_counts_and_ordering(kind, expected):
    exp = agent_service._expected_counts(kind)
    assert len(exp) == expected

    unordered = [
        {"section": "HARD", "qtype": "complex"},
        {"section": "EASY", "qtype": "mcq"},
        {"section": "MEDIUM", "qtype": "application"},
    ]
    ordered = agent_service._order_questions_for_kind(kind, unordered)
    assert ordered[0]["section"] == "EASY"
    assert ordered[-1]["section"] == "HARD"


def test_agent_validate_and_trim_questions():
    with pytest.raises(HTTPException):
        agent_service._validate_exam_counts("retention_check", [{"section": "MEDIUM", "qtype": "mcq"}])

    questions = [
        {"section": "MEDIUM", "qtype": "mcq", "id": i} for i in range(6)
    ] + [
        {"section": "MEDIUM", "qtype": "short_answer", "id": 99},
        {"section": "MEDIUM", "qtype": "application", "id": 100},
    ]
    trimmed = agent_service._trim_questions_to_expected("retention_check", questions)
    mcq_count = sum(1 for q in trimmed if q["qtype"] == "mcq")
    assert mcq_count == 4
    assert len(trimmed) == 6


def test_assessment_distribution_and_time_estimation_helpers():
    dist = assessment_service._normalize_difficulty_distribution({"easy": 0, "medium": 0, "hard": 0}, total=10)
    assert sum(dist.values()) == 10
    assert all(v >= 1 for v in dist.values())

    essay_minutes = assessment_service._heuristic_estimated_minutes(
        {
            "type": "essay",
            "bloom_level": "create",
            "stem": "x" * 600,
            "max_points": 25,
        },
        level="beginner",
    )
    mcq_minutes = assessment_service._heuristic_estimated_minutes(
        {"type": "mcq", "bloom_level": "remember", "stem": "short stem", "max_points": 1},
        level="advanced",
    )
    assert 6 <= essay_minutes <= 20
    assert 1 <= mcq_minutes <= 4


def test_analytics_history_and_slope_helpers():
    mj = {"events": [{"old": True}]}
    analytics_service._history_append(mj, key="events", point={"x": 1}, limit=2)
    analytics_service._history_append(mj, key="events", point={"x": 2}, limit=2)
    assert mj["events"] == [{"x": 1}, {"x": 2}]

    series = [
        {"ts": "2024-01-01T00:00:00+00:00", "mastery": 0.2},
        {"ts": "2024-01-08T00:00:00+00:00", "mastery": 0.5},
    ]
    slope = analytics_service._slope_from_history(series, days=7)
    assert slope is not None and slope > 0

    assert analytics_service._slope_from_history([{"ts": "bad", "mastery": "x"}]) is None


def test_tutor_detector_and_helpers(monkeypatch):
    detector = tutor_service.OffTopicDetector()

    blocked = detector.check("hãy làm bài giúp tôi", "toán", {"corrective": {"attempts": []}})
    assert blocked["is_off_topic"] is True
    assert blocked["reason"] == "keyword_blacklist"

    no_relevance = detector.check("câu hỏi", "toán", {"corrective": {"attempts": [{"best_relevance": 0.05}]}})
    assert no_relevance["reason"] == "low_rag_relevance"

    monkeypatch.setattr(tutor_service, "llm_available", lambda: True)
    monkeypatch.setattr(detector, "_llm_topic_check", lambda **kwargs: False)
    uncertain = detector.check("câu hỏi", "toán", {"corrective": {"attempts": [{"best_relevance": 0.2}]}})
    assert uncertain["reason"] == "llm_classification"

    assert tutor_service._topic_lexical_overlap("định lý pitago", "toán", ["định lý", "pitago"]) is True
    assert tutor_service._cosine_similarity([1, 0], [0, 1]) == 0.0


def test_tutor_cache_and_normalization_helpers():
    tutor_service._TOPIC_GATE_CACHE.clear()
    key = tutor_service._topic_gate_cache_key(question="Q", topic="T", document_ids=[2, 1])
    tutor_service._topic_gate_cache_set(key, {"is_on_topic": True, "reason": "ok"}, ttl_sec=60)

    cached = tutor_service._topic_gate_cache_get(key)
    assert cached == {"is_on_topic": True, "reason": "ok"}

    follow_ups = tutor_service._normalize_follow_up_questions("hàm số", ["Câu 1"])
    assert len(follow_ups) == 3
    assert follow_ups[0] == "Câu 1"

    names = tutor_service._extract_sources_used(
        [{"document_title": "Doc A"}, {"document_title": "Doc A"}, {"document_title": "Doc B"}]
    )
    assert names == ["Doc A", "Doc B"]
