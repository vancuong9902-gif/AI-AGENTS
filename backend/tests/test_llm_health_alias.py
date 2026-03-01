from fastapi.testclient import TestClient

from app.main import app


def test_llm_health_alias_matches_status_route():
    client = TestClient(app)

    status_res = client.get('/api/llm/status')
    health_res = client.get('/api/llm/health')

    assert status_res.status_code == 200
    assert health_res.status_code == 200

    status_body = status_res.json()
    health_body = health_res.json()
    assert status_body["data"] == health_body["data"]
    assert status_body["error"] == health_body["error"]
    assert status_body["request_id"]
    assert health_body["request_id"]
