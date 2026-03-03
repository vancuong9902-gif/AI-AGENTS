from fastapi.testclient import TestClient

from app.main import create_app
from app.models.user import User


def _register_payload(email: str):
    return {
        "name": "Nguyen Van A",
        "email": email,
        "password": "password123",
        "role": "student",
    }


def test_register_success_and_duplicate_conflict(db_session):
    app = create_app(auth_enabled=True)

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    from app.api.deps import get_db

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as client:
        first = client.post('/api/auth/register', json=_register_payload('duplicate@test.local'))
        assert first.status_code == 201
        first_body = first.json()
        assert first_body['error'] is None
        assert first_body['data']['user']['email'] == 'duplicate@test.local'
        assert first_body['data']['token']['access_token']

        second = client.post('/api/auth/register', json=_register_payload('duplicate@test.local'))
        assert second.status_code in {400, 409}
        second_body = second.json()
        assert second_body['detail']['code'] == 'EMAIL_EXISTS'

    app.dependency_overrides.clear()


def test_register_accepts_json_content_type_header(db_session):
    app = create_app(auth_enabled=True)

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    from app.api.deps import get_db

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as client:
        resp = client.post(
            '/api/auth/register',
            headers={'Content-Type': 'application/json'},
            json=_register_payload('content-type@test.local'),
        )
        assert resp.status_code == 201

    app.dependency_overrides.clear()


def test_register_hashes_password(db_session):
    app = create_app(auth_enabled=True)

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    from app.api.deps import get_db

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as client:
        email = 'hash@test.local'
        resp = client.post('/api/auth/register', json=_register_payload(email))
        assert resp.status_code == 201

    created = db_session.query(User).filter(User.email == email).first()
    assert created is not None
    assert created.password_hash is not None
    assert created.password_hash != 'password123'

    app.dependency_overrides.clear()
