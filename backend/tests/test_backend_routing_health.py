from fastapi.testclient import TestClient

from app.main import create_app


def test_root_endpoint_returns_api_running_message():
    client = TestClient(create_app(auth_enabled=False))
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "API running"}


def test_health_endpoint_available_with_and_without_api_prefix():
    client = TestClient(create_app(auth_enabled=False))

    direct = client.get("/health")
    api_prefixed = client.get("/api/health")

    assert direct.status_code == 200
    assert api_prefixed.status_code == 200
    assert direct.json()["status"] == "ok"
    assert api_prefixed.json()["status"] == "ok"
