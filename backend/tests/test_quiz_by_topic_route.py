from types import SimpleNamespace

from app.api.routes import quiz


def test_quiz_by_topic_returns_wrapped_payload(monkeypatch):
    captured = {}

    def _fake(db, topic_id, level, user_id):
        captured.update({"topic_id": topic_id, "level": level, "user_id": user_id})
        return {"quiz_set_id": 12, "questions": [{"question_id": 1}]}

    monkeypatch.setattr(quiz, "get_or_create_practice_quiz_set_by_topic", _fake)

    req = SimpleNamespace(state=SimpleNamespace(request_id="rid-1"))
    out = quiz.quiz_by_topic(request=req, topic_id=9, level="easy", user_id=3, db=object())

    assert captured == {"topic_id": 9, "level": "easy", "user_id": 3}
    assert out["request_id"] == "rid-1"
    assert out["error"] is None
    assert out["data"]["quiz_set_id"] == 12
