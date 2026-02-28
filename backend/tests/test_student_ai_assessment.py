from types import SimpleNamespace

from app.services.analytics_service import generate_student_ai_assessment


class _FakeQuery:
    def __init__(self, row):
        self._row = row

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._row


class _FakeDB:
    def query(self, *args, **kwargs):
        return _FakeQuery(SimpleNamespace(full_name="HS A"))


def test_generate_student_ai_assessment_fallback(monkeypatch):
    monkeypatch.setattr("app.services.analytics_service.llm_available", lambda: False)

    db = _FakeDB()
    entry = SimpleNamespace(score_percent=45, breakdown_json=[])
    final = SimpleNamespace(score_percent=70, breakdown_json=[])

    out = generate_student_ai_assessment(db=db, user_id=101, entry_attempt=entry, final_attempt=final)
    assert "HS A" in out
    assert "tiến bộ" in out.lower() or "tăng" in out.lower()
