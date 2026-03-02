from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from app.services import adaptive_policy_service as aps
from app.services import agent_service, analytics_service, assessment_service, tutor_service, vector_store


@pytest.mark.parametrize(
    "difficulty,expected",
    [("hard", 2), ("medium", 1), ("easy", 0), (None, 0), ("unknown", 0)],
)
def test_adaptive_difficulty_conversion_roundtrip(difficulty, expected):
    assert aps._difficulty_to_int(difficulty) == expected
    assert aps._int_to_difficulty(expected) in {"easy", "medium", "hard"}


def test_adaptive_build_state_uses_topic_mastery_and_bins():
    profile = SimpleNamespace(
        level="beginner",
        mastery_json={
            "mastery": 0.3,
            "avg_time_per_item_sec": 30,
            "engagement": 0.4,
            "topic_mastery": {"topicA": 0.9},
        },
    )
    state = aps.build_state(
        profile=profile,
        topic="topicA",
        recent_accuracy=0.83,
        avg_time_per_item_sec=71,
        engagement=0.76,
        current_difficulty="medium",
    )
    assert state["mastery"] == 0.9
    assert state["bins"] == {"acc": 2, "time": 2, "eng": 2, "mastery": 2, "difficulty": 1}
    assert aps._state_key(state).startswith("a2_t2")


def test_adaptive_q_select_and_update_flow(monkeypatch):
    state = {"bins": {"acc": 1, "time": 0, "eng": 1, "mastery": 1, "difficulty": 0}}
    q = {}
    monkeypatch.setattr(aps.random, "random", lambda: 0.9)
    action, dbg = aps._q_select(state, q, epsilon=0.1)
    assert action == "increase_difficulty"
    assert dbg["strategy"] == "greedy_q"

    aps._q_update(q, state=state, action="continue", reward=0.8, next_state=None, alpha=0.5, gamma=0.9)
    sk = aps._state_key(state)
    assert q[sk]["continue"] == pytest.approx(0.4)


def test_analytics_core_math_helpers_and_weights():
    assert analytics_service._sigmoid(0) == pytest.approx(0.5)
    assert analytics_service._clip(1.5, 0.0, 1.0) == 1.0
    assert analytics_service._normalize_weights({"w1_knowledge": -1, "w2_improvement": 0}) == {
        "w1_knowledge": 0.25,
        "w2_improvement": 0.25,
        "w3_engagement": 0.25,
        "w4_retention": 0.25,
    }


def test_analytics_compute_knowledge_document_scope_and_fallback():
    mj = {
        "topic_mastery": {"doc1:topicA": 0.8, "doc1:topicB": 0.6, "doc2:topicA": 0.1},
        "__last_exam_score_percent__": 0.42,
    }
    assert analytics_service.compute_knowledge(mj, document_id=1) == pytest.approx(0.7)
    assert analytics_service.compute_knowledge({"__last_exam_score_percent__": 0.42}, document_id=1) == pytest.approx(0.42)


@pytest.mark.parametrize(
    "seconds,expected",
    [(0, 0.0), (5, 0.0), (15, 0.5), (45, 1.0), (120, pytest.approx(0.833333, rel=1e-3)), (300, 0.2)],
)
def test_analytics_time_quality_branches(seconds, expected):
    assert analytics_service._time_quality(seconds) == expected


def test_agent_helpers_for_text_and_exam_stats(monkeypatch):
    assert agent_service._keyword_score("định lý pitago", ["định", "pitago", "hình học"]) > 0
    assert agent_service._keyword_score("", ["x"]) == 0
    assert agent_service._difficulty_norm("H") == "hard"
    assert agent_service._topic_key(2, 3, " Tam giác ") == "doc2:topic3:Tam giác"

    monkeypatch.setattr(agent_service, "llm_available", lambda: False)
    assert agent_service._llm_topic_recap(language="vi", packed_chunks=[], topic_title="Toán") == ""

    stats = agent_service.final_exam_analytics(
        [
            {"qtype": "mcq", "is_correct": True, "score_points": 1, "max_points": 1},
            {"qtype": "essay", "is_correct": False, "score_points": 0, "max_points": 2},
        ]
    )
    assert stats["by_question_type_percent"]["mcq"] == 100
    assert "essay" in stats["weak_areas"]


def test_assessment_duration_and_level_helpers():
    assert assessment_service.parse_duration_seconds("midterm;duration=1800") == 1800
    assert assessment_service.parse_duration_seconds("midterm") is None
    assert assessment_service.clean_level_text("a;duration=900;;b") == "a;b"
    assert assessment_service._normalize_assessment_kind("assessment") == "midterm"
    assert assessment_service._normalize_assessment_kind("final") == "final_exam"
    assert assessment_service._level_from_total(90, essay_percent=20, gate_essay=True) == "intermediate"
    assert assessment_service._diagnostic_pre_level(79) == "intermediate"


def test_assessment_content_helpers_and_review_breakdown():
    payload = assessment_service._build_study_materials_payload(level_key="yeu", weak_topics=["hàm số"])
    assert payload["level"] == "yeu"
    assert payload["exercises"][0]["estimated_minutes"] == 20

    scores = assessment_service._split_scores_from_breakdown(
        [
            {"type": "mcq", "max_points": 2, "score_points": 2},
            {"type": "essay", "max_points": 3, "score_points": 0, "graded": False},
        ]
    )
    assert scores["pending"] is True
    assert scores["total_percent"] == 70

    assert assessment_service._topic_mastery_from_breakdown([
        {"topic": "Đại số", "max_points": 4, "score_points": 2},
    ]) == {"đại số": 0.5}
    assert assessment_service._rag_query_for_topic("Tài liệu", "advanced").startswith("tổng hợp")


def test_tutor_helpers_for_gate_and_practice(monkeypatch):
    assert tutor_service._extract_referenced_topic("hãy hỏi topic tam giác vuông") == "tam giác vuông"
    assert tutor_service._extract_referenced_topic("chỉ câu hỏi") == "chỉ câu hỏi"
    assert tutor_service._is_practice_request("hãy kiểm tra tôi") is True

    monkeypatch.setattr(tutor_service, "llm_available", lambda: False)
    gate = tutor_service._llm_offtopic_gate(question="q", topic="toán", evidence_previews=[])
    assert gate["reason"] == "gate_disabled"

    grade = tutor_service._grade_practice_answer(topic="toán", question="q", answer="ngắn", chunks=[])
    assert grade["score"] == 0


def test_vector_store_add_chunks_dedup_and_dimension_reset(monkeypatch):
    class _Idx:
        def __init__(self, d):
            self.d = d
            self.ntotal = 0
            self.added = []

        def add(self, mat):
            self.ntotal += len(mat)
            self.added.append(mat)

    class _Faiss:
        def IndexFlatIP(self, d):
            return _Idx(d)

        def write_index(self, _index, _path):
            return None

    monkeypatch.setattr(vector_store, "FAISS_AVAILABLE", True)
    monkeypatch.setattr(vector_store, "np", np)
    monkeypatch.setattr(vector_store, "faiss", _Faiss())
    monkeypatch.setattr(vector_store, "is_enabled", lambda: True)
    monkeypatch.setattr(vector_store, "embed_texts", lambda texts, model=None: [[1.0, 0.0] for _ in texts])
    monkeypatch.setattr(vector_store, "_persist", lambda: None)

    vector_store._index = _Idx(3)
    vector_store._meta = [{"chunk_id": 1, "document_id": 1}]
    vector_store._ready = True

    out = vector_store.add_chunks([
        {"chunk_id": 1, "document_id": 1, "text": "dup"},
        {"chunk_id": 2, "document_id": 1, "text": "new"},
        {"chunk_id": 2, "document_id": 1, "text": "dup-in-call"},
    ])

    assert out["added"] == 1
    assert out["skipped"] >= 2
    assert vector_store._index.d == 2
    assert vector_store._meta[-1]["chunk_id"] == 2
