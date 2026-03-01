from __future__ import annotations

from app.services import tutor_service


class _Q:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return self._rows


class _DB:
    def query(self, *entities):
        if len(entities) == 2:
            return _Q([(1, "Đại số 10")])
        return _Q([("Phương trình bậc hai", "Tổng quan", ["delta", "nghiệm"])])


def test_is_question_on_topic_llm_success(monkeypatch):
    monkeypatch.setattr(tutor_service.settings, "TUTOR_LLM_OFFTOPIC_ENABLED", True)
    monkeypatch.setattr(tutor_service, "llm_available", lambda: True)
    monkeypatch.setattr(
        tutor_service,
        "chat_json",
        lambda **_kwargs: {
            "is_on_topic": False,
            "reason": "outside_scope",
            "suggested_questions": ["Công thức nghiệm là gì?", "Delta có ý nghĩa gì?"],
        },
    )

    got = tutor_service._is_question_on_topic_llm(
        _DB(),
        question="Ai vô địch World Cup 2022?",
        topic="Phương trình bậc hai",
        document_ids=[1],
    )

    assert got["is_on_topic"] is False
    assert got["reason"] == "outside_scope"
    assert len(got["suggested_questions"]) >= 2


def test_is_question_on_topic_llm_fallback_when_llm_fails(monkeypatch):
    monkeypatch.setattr(tutor_service.settings, "TUTOR_LLM_OFFTOPIC_ENABLED", True)
    monkeypatch.setattr(tutor_service, "llm_available", lambda: True)

    def _boom(**_kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(tutor_service, "chat_json", _boom)

    got = tutor_service._is_question_on_topic_llm(
        _DB(),
        question="Delta là gì?",
        topic="Phương trình bậc hai",
        document_ids=[1],
    )

    assert got["reason"] == "lexical_fallback_after_llm_error"
    assert isinstance(got["is_on_topic"], bool)
    assert len(got["suggested_questions"]) > 0
