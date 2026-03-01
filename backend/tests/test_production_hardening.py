from fastapi import UploadFile, File
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings


@app.get("/api/_raise_test")
def _raise_test():
    raise RuntimeError("secret stack detail")


@app.post("/api/_upload_test")
def _upload_test(file: UploadFile = File(...)):
    return {"name": file.filename}


def test_production_hides_internal_error_details():
    client = TestClient(app)
    old_env = settings.ENV
    settings.ENV = "production"
    try:
        res = client.get("/api/_raise_test")
    finally:
        settings.ENV = old_env

    body = res.json()
    assert res.status_code == 500
    assert body["error"]["message"] == "Internal server error"
    assert body["request_id"]


def test_upload_limit_returns_413():
    client = TestClient(app)
    old_max = settings.MAX_UPLOAD_MB
    settings.MAX_UPLOAD_MB = 1
    try:
        data = b"x" * (1024 * 1024 + 10)
        res = client.post("/api/_upload_test", files={"file": ("big.txt", data, "text/plain")})
    finally:
        settings.MAX_UPLOAD_MB = old_max

    body = res.json()
    assert res.status_code == 413
    assert body["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_rate_limit_heavy_endpoint():
    client = TestClient(app)
    old_rate = settings.RATE_LIMIT_REQUESTS_PER_MINUTE
    settings.RATE_LIMIT_REQUESTS_PER_MINUTE = 1
    try:
        first = client.post("/api/tutor/chat", json={"question": "Hi", "top_k": 1})
        second = client.post("/api/tutor/chat", json={"question": "Hi", "top_k": 1})
    finally:
        settings.RATE_LIMIT_REQUESTS_PER_MINUTE = old_rate

    # endpoint may return non-200 on first call depending on fixtures, but second should be rate-limited
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "RATE_LIMITED"
    assert first.headers.get("X-Request-ID")
