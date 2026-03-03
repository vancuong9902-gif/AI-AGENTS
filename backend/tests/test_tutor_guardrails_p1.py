from types import SimpleNamespace

from app.services import tutor_service


class _FakeDB:
    def add(self, _):
        return None

    def commit(self):
        return None


def test_tutor_rejects_offtopic_without_llm(monkeypatch):
    monkeypatch.setattr(tutor_service, "ensure_user_exists", lambda *a, **k: None)
    monkeypatch.setattr(tutor_service, "llm_available", lambda: False)

    out = tutor_service.tutor_chat(
        _FakeDB(),
        user_id=7,
        question="Thời tiết hôm nay thế nào?",
        allowed_topics=["Hàm số bậc nhất", "Phương trình"],
        document_ids=[1],
    )

    assert out["is_off_topic"] is True
    assert "chỉ có thể hỗ trợ" in out["answer_md"].lower()
    assert out["retrieval"]["guardrail"] == "keyword_set"
