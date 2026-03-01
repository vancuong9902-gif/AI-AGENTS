from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.api.routes import auth as auth_module
from app.api.routes.auth import login_guard, otp_store, router
from app.models.user import User


SQLALCHEMY_DATABASE_URL = "sqlite:///./test_auth_security.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)



def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _build_client() -> TestClient:
    User.__table__.drop(bind=engine, checkfirst=True)
    User.__table__.create(bind=engine, checkfirst=True)
    otp_store._records.clear()
    login_guard._attempts.clear()
    login_guard._locked_until.clear()
    auth_module.get_password_hash = lambda pwd: f"hashed::{pwd}"
    auth_module.verify_password = lambda plain, hashed: hashed == f"hashed::{plain}"
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _register_payload(email: str = "sv01@gmail.com") -> dict:
    return {
        "email": email,
        "password": "StrongPass1",
        "full_name": "Nguyen Van A",
        "phone_number": "0912345678",
        "major": "Cong nghe thong tin",
        "class_name": "CNTT-K17",
        "role": "student",
    }


def test_register_rejects_non_gmail():
    client = _build_client()
    resp = client.post("/api/auth/register", json={**_register_payload(), "email": "abc@yahoo.com"})
    assert resp.status_code == 422


def test_register_verify_and_login_success():
    client = _build_client()

    register_resp = client.post("/api/auth/register", json=_register_payload("teacher01@gmail.com"))
    assert register_resp.status_code == 200

    otp = otp_store._records["verify_email:teacher01@gmail.com"].code
    verify_resp = client.post(
        "/api/auth/verify-email",
        json={"email": "teacher01@gmail.com", "otp": otp},
    )
    assert verify_resp.status_code == 200

    login_resp = client.post(
        "/api/auth/login-json",
        json={"email": "teacher01@gmail.com", "password": "StrongPass1"},
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["data"]["token"]["access_token"]


def test_login_bruteforce_lock_after_5_failures():
    client = _build_client()
    client.post("/api/auth/register", json=_register_payload("student02@gmail.com"))
    otp = otp_store._records["verify_email:student02@gmail.com"].code
    client.post("/api/auth/verify-email", json={"email": "student02@gmail.com", "otp": otp})

    for _ in range(5):
        bad = client.post(
            "/api/auth/login-json",
            json={"email": "student02@gmail.com", "password": "wrong-password"},
        )
        assert bad.status_code == 401

    locked = client.post(
        "/api/auth/login-json",
        json={"email": "student02@gmail.com", "password": "wrong-password"},
    )
    assert locked.status_code == 429

    login_guard._attempts.clear()
    login_guard._locked_until.clear()
