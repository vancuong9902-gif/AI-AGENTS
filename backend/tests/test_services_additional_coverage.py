from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

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

from app.services import agent_service, analytics_service, assessment_service, text_quality, tutor_service


class _ChainQuery:
    def __init__(self, rows):
        self._rows = list(rows)

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)


class _AssessmentDB:
    def __init__(self, source_rows):
        self.source_rows = source_rows

    def query(self, *models, **kwargs):
        if len(models) == 2:
            return _ChainQuery(self.source_rows)
        raise AssertionError(f"Unexpected query: {models}")


def test_generate_mcq_explanation_map_prefers_llm_response(monkeypatch):
    db = _AssessmentDB(
        source_rows=[
            (
                SimpleNamespace(id=10, text="Định nghĩa phép cộng"),
                SimpleNamespace(title="Toán 5"),
            )
        ]
    )
    quiz_set = SimpleNamespace(document_ids_json="[1,2]")
    q = SimpleNamespace(id=1, stem="2 + 2 bằng mấy?", options=["1", "3", "4"], correct_index=2, sources=[{"chunk_id": 10}])

    monkeypatch.setattr(assessment_service, "pack_chunks", lambda chunks, **kwargs: chunks)
    monkeypatch.setattr(assessment_service, "llm_available", lambda: True)
    monkeypatch.setattr(assessment_service, "chat_text", lambda **kwargs: "Giải thích từ tài liệu.")

    out = assessment_service._generate_mcq_explanation_map(
        db,
        quiz_set=quiz_set,
        questions_by_id={1: q},
        breakdown=[{"question_id": 1, "type": "mcq", "score_points": 0, "max_points": 1, "chosen": 1, "correct": 2}],
    )

    assert out == {"1": "Giải thích từ tài liệu."}


def test_generate_mcq_explanation_map_falls_back_when_llm_unavailable(monkeypatch):
    db = _AssessmentDB(source_rows=[])
    quiz_set = SimpleNamespace(document_ids_json=None)
    q = SimpleNamespace(id=2, stem="Khái niệm ma trận", options=["A", "B"], correct_index=0, sources=[])

    monkeypatch.setattr(assessment_service, "retrieve_and_log", lambda *args, **kwargs: {"chunks": [{"chunk_id": 2, "title": "ĐS", "text": "Ma trận"}]})
    monkeypatch.setattr(assessment_service, "pack_chunks", lambda chunks, **kwargs: chunks)
    monkeypatch.setattr(assessment_service, "llm_available", lambda: False)

    out = assessment_service._generate_mcq_explanation_map(
        db,
        quiz_set=quiz_set,
        questions_by_id={2: q},
        breakdown=[{"question_id": 2, "type": "mcq", "score_points": 0, "max_points": 1}],
    )

    assert "đáp án đúng là 'A'" in out["2"]


def test_agent_llm_doc_summary_fallback_when_llm_errors(monkeypatch):
    monkeypatch.setattr(agent_service, "llm_available", lambda: True)
    monkeypatch.setattr(agent_service, "chat_json", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    assert agent_service._llm_doc_summary("Nội dung ngắn", title="Doc") == "Nội dung ngắn"


def test_analytics_datetime_and_sigmoid_helpers_are_stable():
    now = analytics_service._utcnow()
    assert now.tzinfo is not None

    iso = analytics_service._iso(datetime(2025, 1, 1, 12, 30, 45, 999999, tzinfo=timezone.utc))
    assert iso == "2025-01-01T12:30:45+00:00"

    assert analytics_service._sigmoid(10) > 0.99
    assert analytics_service._sigmoid(-10) < 0.01


def test_text_quality_handles_empty_and_symbol_heavy_inputs():
    assert text_quality.quality_report("")["reasons"] == ["empty", "too_short", "low_letter_ratio"]

    noisy = "{}[]();:=<>/*+\\|`~^$#@ 123 456 789"
    report = text_quality.quality_report(noisy)
    assert report["score"] <= 0.2
    assert "low_letter_ratio" in report["reasons"]


def test_tutor_llm_topic_check_and_gate_validation(monkeypatch):
    detector = tutor_service.OffTopicDetector()

    monkeypatch.setattr(tutor_service, "chat_text", lambda **kwargs: "NO")
    assert detector._llm_topic_check("abc", "toán") is False

    monkeypatch.setattr(tutor_service, "chat_text", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("x")))
    assert detector._llm_topic_check("abc", "toán") is True

    monkeypatch.setattr(tutor_service, "llm_available", lambda: False)
    with pytest.raises(RuntimeError, match="llm_not_available"):
        tutor_service._is_question_on_topic_llm_gate(SimpleNamespace(), "câu hỏi", None, [1])
