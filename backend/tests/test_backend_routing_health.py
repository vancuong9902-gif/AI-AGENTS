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


def test_docs_endpoints_are_available_at_default_and_legacy_paths():
    client = TestClient(create_app(auth_enabled=False))

    docs_default = client.get("/docs")
    docs_legacy = client.get("/api/v1/docs")
    redoc_default = client.get("/redoc")
    redoc_legacy = client.get("/api/v1/redoc")
    openapi_default = client.get("/openapi.json")
    openapi_legacy = client.get("/api/v1/openapi.json")

    assert docs_default.status_code == 200
    assert docs_legacy.status_code == 200
    assert redoc_default.status_code == 200
    assert redoc_legacy.status_code == 200
    assert openapi_default.status_code == 200
    assert openapi_legacy.status_code == 200
    assert openapi_default.json()["openapi"].startswith("3.")
    assert openapi_legacy.json()["openapi"].startswith("3.")
