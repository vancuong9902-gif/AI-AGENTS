from __future__ import annotations

import pytest

from app.core import security


def test_verify_password_handles_exceptions(monkeypatch):
    monkeypatch.setattr(security.pwd_context, "verify", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("x")))
    assert security.verify_password("abc123", "hash") is False


def test_access_token_and_decode():
    token = security.create_access_token(subject="user1")
    payload = security.decode_token(token)
    assert payload.get("sub") == "user1"


def test_decode_invalid_token_raises():
    with pytest.raises(Exception):
        security.decode_token("invalid.token")
