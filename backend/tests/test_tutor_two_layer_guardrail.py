from __future__ import annotations

from app.schemas.tutor import TutorChatRequest
from app.services import ai_tutor_service, tutor_service


class _FakeDB:
    def add(self, _):
        return None

    def commit(self):
        return None

    def query(self, *args, **kwargs):
        raise AssertionError("query should not be called in these unit tests")


def test_layer1_keyword_reject(monkeypatch):
    monkeypatch.setattr(tutor_service, "ensure_user_exists", lambda *a, **k: None)
    monkeypatch.setattr(tutor_service, "auto_document_ids_for_query", lambda *a, **k: [])
    monkeypatch.setattr(tutor_service, "_topic_references_for_guardrail", lambda *a, **k: ["phương trình bậc hai", "delta"])

    called = {"llm": 0}

    def _never(**_kwargs):
        called["llm"] += 1
        return True

    monkeypatch.setattr(tutor_service, "_llm_yes_no_topic_gate", _never)

    out = tutor_service.tutor_chat(
        _FakeDB(),
        user_id=1,
        question="Ai vô địch World Cup 2022?",
        topic="Phương trình bậc hai",
        allowed_topics=["Phương trình bậc hai"],
    )

    assert out["is_off_topic"] is True
    assert out["off_topic_reason"] == "layer1_keyword_reject"
    assert out["retrieval"]["offtopic_layer"] == 1
    assert called["llm"] == 0


def test_layer2_llm_reject(monkeypatch):
    monkeypatch.setattr(tutor_service, "ensure_user_exists", lambda *a, **k: None)
    monkeypatch.setattr(tutor_service, "auto_document_ids_for_query", lambda *a, **k: [])
    monkeypatch.setattr(tutor_service, "_topic_references_for_guardrail", lambda *a, **k: ["phương trình bậc hai", "delta"])
    monkeypatch.setattr(tutor_service, "_llm_yes_no_topic_gate", lambda **_kwargs: False)

    out = tutor_service.tutor_chat(
        _FakeDB(),
        user_id=2,
        question="delta trong phương trình bậc hai là gì?",
        topic="Phương trình bậc hai",
        allowed_topics=["Phương trình bậc hai"],
    )

    assert out["is_off_topic"] is True
    assert out["off_topic_reason"] == "layer2_llm_reject"
    assert out["retrieval"]["offtopic_layer"] == 2
    assert len(out["suggested_questions"]) == 3


def test_run_tutor_chat_returns_relevance_contract(monkeypatch):
    monkeypatch.setattr(ai_tutor_service, "get_json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ai_tutor_service, "set_json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        ai_tutor_service,
        "tutor_chat",
        lambda **_kwargs: {
            "is_off_topic": False,
            "answer_md": "Câu trả lời mẫu",
            "suggested_questions": ["Q1", "Q2", "Q3"],
            "suggested_topics": ["Đại số"],
            "sources_used": ["Tài liệu 1"],
        },
    )

    payload = TutorChatRequest(user_id=11, question="Hỏi", topic="Đại số")
    out = ai_tutor_service.run_tutor_chat(_FakeDB(), payload)

    assert out["is_relevant"] is True
    assert out["response"] == "Câu trả lời mẫu"
    assert out["suggested_questions"] == ["Q1", "Q2", "Q3"]
    assert out["references"][0] == "Đại số"
