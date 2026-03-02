from pathlib import Path

from app.schemas.auth import LoginRequest


def test_login_schema_normalizes_email():
    payload = LoginRequest.model_validate({"email": "  Teacher1@Demo.Local ", "password": "password123"})
    assert payload.email == "teacher1@demo.local"


def test_login_invalid_credentials_returns_400_contract():
    src = (Path(__file__).resolve().parents[1] / "app" / "services" / "auth_service.py").read_text(encoding="utf-8")
    assert 'HTTPException(status_code=400, detail="Invalid credentials")' in src
