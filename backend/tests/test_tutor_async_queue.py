from fastapi.testclient import TestClient

from app.main import app


def test_tutor_async_endpoint_enqueues_job(monkeypatch):
    def _fake_enqueue(fn, *args, **kwargs):
        return {"job_id": "job-123", "queued": True, "sync_executed": False, "result": None}

    monkeypatch.setattr("app.api.routes.tutor.enqueue", _fake_enqueue)

    client = TestClient(app)
    res = client.post(
        "/api/v1/tutor/chat/async",
        json={"user_id": 1, "question": "What is gradient descent?", "top_k": 3},
    )

    assert res.status_code == 202
    assert res.json()["job_id"] == "job-123"
    assert res.json()["queued"] is True
