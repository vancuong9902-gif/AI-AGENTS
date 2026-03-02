from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import deps
from app.tasks import ai_tasks, drift_tasks, index_tasks


class _FakeUserQuery:
    def __init__(self, user):
        self._user = user

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._user


class _FakeDBForUser:
    def __init__(self, user):
        self._user = user

    def query(self, _model):
        return _FakeUserQuery(self._user)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        (" teacher ", "teacher"),
        ("ADMIN", "admin"),
        ("unknown", None),
    ],
)
def test_normalize_role(raw, expected):
    assert deps._normalize_role(raw) == expected


def test_resolve_jwt_user_paths(monkeypatch):
    db = _FakeDBForUser(SimpleNamespace(id=5))

    assert deps._resolve_jwt_user(db, None) is None

    monkeypatch.setattr(deps, "safe_decode_token", lambda _token: None)
    assert deps._resolve_jwt_user(db, "token") is None

    monkeypatch.setattr(deps, "safe_decode_token", lambda _token: {"no_sub": 1})
    assert deps._resolve_jwt_user(db, "token") is None

    monkeypatch.setattr(deps, "safe_decode_token", lambda _token: {"sub": "abc"})
    assert deps._resolve_jwt_user(db, "token") is None

    monkeypatch.setattr(deps, "safe_decode_token", lambda _token: {"sub": "5"})
    user = deps._resolve_jwt_user(db, "token")
    assert user.id == 5


def test_get_current_user_optional_auth_modes(monkeypatch):
    db = object()

    monkeypatch.setattr(deps.settings, "AUTH_ENABLED", True)
    monkeypatch.setattr(deps, "_resolve_jwt_user", lambda *_args, **_kwargs: "jwt-user")
    assert deps.get_current_user_optional(db=db, token="t", x_user_id=None, x_user_role=None) == "jwt-user"

    monkeypatch.setattr(deps.settings, "AUTH_ENABLED", False)
    assert deps.get_current_user_optional(db=db, token=None, x_user_id=None, x_user_role=None) is None

    assert deps.get_current_user_optional(db=db, token=None, x_user_id="x", x_user_role="student") is None

    called = []
    monkeypatch.setattr(deps, "ensure_user_exists", lambda _db, uid, role: called.append((uid, role)) or {"id": uid, "role": role})
    monkeypatch.setattr(deps.settings, "DEMO_SEED", False)

    admin_demoted = deps.get_current_user_optional(db=db, token=None, x_user_id="7", x_user_role="admin")
    assert admin_demoted["role"] == "student"

    teacher_demoted = deps.get_current_user_optional(db=db, token=None, x_user_id="8", x_user_role="teacher")
    assert teacher_demoted["role"] == "student"

    monkeypatch.setattr(deps.settings, "DEMO_SEED", True)
    teacher_ok = deps.get_current_user_optional(db=db, token=None, x_user_id="9", x_user_role="teacher")
    assert teacher_ok["role"] == "teacher"

    default_student = deps.get_current_user_optional(db=db, token=None, x_user_id="10", x_user_role=None)
    assert default_student["role"] == "student"
    assert called[0] == (7, "student")


def test_require_user_teacher_admin():
    with pytest.raises(HTTPException) as unauth:
        deps.require_user(None)
    assert unauth.value.status_code == 401

    inactive = SimpleNamespace(is_active=False)
    with pytest.raises(HTTPException) as forbidden:
        deps.require_user(inactive)
    assert forbidden.value.status_code == 403

    teacher = SimpleNamespace(role="teacher", is_active=True)
    assert deps.require_teacher(teacher) is teacher

    with pytest.raises(HTTPException):
        deps.require_teacher(SimpleNamespace(role="student", is_active=True))

    admin = SimpleNamespace(role="admin", is_active=True)
    assert deps.require_admin(admin) is admin

    with pytest.raises(HTTPException):
        deps.require_admin(SimpleNamespace(role="teacher", is_active=True))


class _FakeChunkQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.closed = False

    def query(self, _model):
        return _FakeChunkQuery(self.rows)

    def close(self):
        self.closed = True


def test_task_index_document_and_rebuild(monkeypatch):
    db = _FakeDB(rows=[SimpleNamespace(id=1, document_id=4, text="hello")])
    monkeypatch.setattr(index_tasks, "SessionLocal", lambda: db)

    monkeypatch.setattr(index_tasks.vector_store, "is_enabled", lambda: False)
    skipped = index_tasks.task_index_document(4)
    assert skipped["skipped"] is True

    monkeypatch.setattr(index_tasks.vector_store, "is_enabled", lambda: True)
    load_calls = []
    monkeypatch.setattr(index_tasks.vector_store, "load_if_exists", lambda: load_calls.append(True))
    monkeypatch.setattr(index_tasks.vector_store, "add_chunks", lambda payload: {"added": len(payload), "payload": payload})

    indexed = index_tasks.task_index_document(4)
    assert indexed["indexed"] is True and indexed["added"] == 1
    assert db.closed is True and load_calls

    db2 = _FakeDB()
    monkeypatch.setattr(index_tasks, "SessionLocal", lambda: db2)
    monkeypatch.setattr(index_tasks.vector_store, "rebuild_from_db", lambda _db: {"reindexed": 3})
    rebuilt = index_tasks.task_rebuild_vector_index()
    assert rebuilt == {"rebuilt": True, "reindexed": 3}
    assert db2.closed is True


def test_task_tutor_chat_and_task_run_drift_check(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(ai_tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(ai_tasks.TutorChatRequest, "model_validate", lambda payload: {"payload": payload})
    monkeypatch.setattr(
        ai_tasks,
        "run_tutor_chat",
        lambda _db, _payload: {
            "b": b"bytes",
            "ba": bytearray(b"arr"),
            "mv": memoryview(b"mem"),
        },
    )
    result = ai_tasks.task_tutor_chat({"text": "hi"})
    assert result["ok"] is True
    assert result["data"] == {"b": "bytes", "ba": "arr", "mv": "mem"}
    assert db.closed is True

    db2 = _FakeDB()
    monkeypatch.setattr(drift_tasks, "SessionLocal", lambda: db2)
    monkeypatch.setattr(drift_tasks, "compute_drift_report", lambda *_args, **_kwargs: {"overall": 0.25})
    monkeypatch.setattr(drift_tasks, "store_drift_report", lambda *_args, **_kwargs: SimpleNamespace(id=99))
    out = drift_tasks.task_run_drift_check(days=5, user_id=1, document_id=2)
    assert out == {"stored": True, "drift_report_id": 99, "overall": 0.25}
    assert db2.closed is True
