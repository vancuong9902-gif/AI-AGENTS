from pydantic import ValidationError

from app.schemas.auth import RegisterRequest


def test_register_schema_accepts_name_alias_and_teacher_role():
    payload = RegisterRequest.model_validate(
        {
            "name": "cuong",
            "email": "cuong05@gmail.com",
            "password": "12345678",
            "role": "teacher",
        }
    )

    assert payload.name == "cuong"
    assert payload.role == "teacher"


def test_register_schema_rejects_short_password():
    try:
        RegisterRequest.model_validate(
            {
                "name": "cuong",
                "email": "cuong05@gmail.com",
                "password": "1234567",
                "role": "teacher",
            }
        )
        raise AssertionError("expected ValidationError")
    except ValidationError as exc:
        assert any(err["loc"][-1] == "password" for err in exc.errors())
