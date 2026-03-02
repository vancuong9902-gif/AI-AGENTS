from app.services import vector_store as s


def test_hash_text_stable():
    assert s._hash_text("abc") == s._hash_text("abc")


def test_status_has_enabled_flag():
    out = s.status()
    assert "semantic_rag_enabled" in out
