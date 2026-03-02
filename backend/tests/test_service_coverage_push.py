from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import tutor_service, user_service, vector_store, vietnamese_font_fix


@pytest.fixture
def client() -> TestClient:
    app: FastAPI = create_app(auth_enabled=False)
    return TestClient(app)


class _Field:
    def __eq__(self, other):
        return ("eq", other)


class _UserModel:
    id = _Field()
    email = _Field()

    def __init__(self, id: int, email: str, full_name: str, role: str):
        self.id = id
        self.email = email
        self.full_name = full_name
        self.role = role


class _FakeQuery:
    def __init__(self, db, model):
        self.db = db
        self.model = model
        self.eq_value = None

    def filter(self, expr):
        self.eq_value = expr[1]
        return self

    def first(self):
        if self.model is _UserModel:
            if isinstance(self.eq_value, int):
                return self.db.users_by_id.get(self.eq_value)
            return self.db.users_by_email.get(self.eq_value)
        return None


class _FakeDB:
    def __init__(self, users_by_id=None, users_by_email=None):
        self.users_by_id = users_by_id or {}
        self.users_by_email = users_by_email or {}
        self.added = []
        self.commit_count = 0
        self.refresh_count = 0

    def query(self, model):
        return _FakeQuery(self, model)

    def add(self, obj):
        self.added.append(obj)
        self.users_by_id[obj.id] = obj
        self.users_by_email[obj.email] = obj

    def commit(self):
        self.commit_count += 1

    def refresh(self, _obj):
        self.refresh_count += 1


def test_client_fixture_smoke(client: TestClient):
    response = client.get("/health")
    assert response.status_code in (200, 404)


def test_ensure_user_exists_updates_role(monkeypatch):
    monkeypatch.setattr(user_service, "User", _UserModel)
    existing = _UserModel(10, "student10@demo.local", "Student 10", "student")
    db = _FakeDB(users_by_id={10: existing})

    out = user_service.ensure_user_exists(db, 10, role="teacher")

    assert out is existing
    assert existing.role == "teacher"
    assert db.commit_count == 1


def test_ensure_user_exists_creates_user_with_unique_email(monkeypatch):
    monkeypatch.setattr(user_service, "User", _UserModel)
    db = _FakeDB(users_by_email={"student11@demo.local": object()})

    out = user_service.ensure_user_exists(db, 11, role="student")

    assert out.id == 11
    assert out.email == "student11-11@demo.local"
    assert db.refresh_count == 1
    assert db.commit_count == 1


def test_offtopic_gate_uses_cache_without_llm(monkeypatch):
    tutor_service._OFFTOPIC_GATE_CACHE.clear()
    key = tutor_service._offtopic_gate_cache_key("câu hỏi", "toán", [2, 1])
    tutor_service._OFFTOPIC_GATE_CACHE[key] = {
        "is_on_topic": False,
        "reason": "cached",
        "matched_topic": "tam giác",
        "expires_at": 9999999999,
    }

    monkeypatch.setattr(tutor_service, "llm_available", lambda: (_ for _ in ()).throw(AssertionError("must not call")))

    got = tutor_service._is_question_on_topic_llm_gate(SimpleNamespace(), "câu hỏi", "toán", [1, 2])
    assert got == (False, "cached", "tam giác")


def test_offtopic_detector_llm_topic_check_yes_and_error(monkeypatch):
    detector = tutor_service.OffTopicDetector()
    monkeypatch.setattr(tutor_service, "chat_text", lambda **kwargs: "YES")
    assert detector._llm_topic_check("hàm số là gì", "toán") is True

    monkeypatch.setattr(tutor_service, "chat_text", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    assert detector._llm_topic_check("hàm số là gì", "toán") is True


def test_vector_store_normalize_and_hash(monkeypatch):
    monkeypatch.setattr(vector_store, "np", np)
    mat = np.array([[3.0, 4.0], [0.0, 0.0]], dtype="float32")
    out = vector_store._normalize(mat)
    assert pytest.approx(float(out[0][0]), rel=1e-6) == 0.6
    assert pytest.approx(float(out[0][1]), rel=1e-6) == 0.8
    assert list(out[1]) == [0.0, 0.0]

    assert vector_store._hash_text(" a   b\n") == vector_store._hash_text("a b")


def test_vector_store_search_not_ready(monkeypatch):
    monkeypatch.setattr(vector_store, "is_enabled", lambda: True)
    monkeypatch.setattr(vector_store, "_ready", False)
    monkeypatch.setattr(vector_store, "_index", None)

    with pytest.raises(RuntimeError, match="Vector index not ready"):
        vector_store.search(SimpleNamespace(), "query")


def test_convert_vni_token_and_llm_repair_paths(monkeypatch):
    assert vietnamese_font_fix._convert_vni_token("d9") == "d9"
    assert vietnamese_font_fix._convert_vni_token("Toa1n") == "Toán"

    garbled = "Toa?n ho□ co? ba?n"

    monkeypatch.setattr(vietnamese_font_fix, "looks_garbled_short_title", lambda _t: True)

    import app.services.llm_service as llm

    monkeypatch.setattr(llm, "llm_available", lambda: False)
    assert vietnamese_font_fix.llm_repair_title_if_needed(garbled) == garbled

    monkeypatch.setattr(llm, "llm_available", lambda: True)
    monkeypatch.setattr(llm, "chat_text", lambda *args, **kwargs: "")
    assert vietnamese_font_fix.llm_repair_title_if_needed(garbled) == garbled


def test_detect_vni_typing_windowed_behavior():
    assert vietnamese_font_fix.detect_vni_typing("Toa1n ho5c lo7p 10", min_matches=2, window_size=10) is True
    assert vietnamese_font_fix.detect_vni_typing("x2 + y2 = z2", min_matches=2, window_size=10) is False
