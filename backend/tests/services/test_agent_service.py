import pytest

from app.services import agent_service as s


@pytest.mark.parametrize("kind", ["diagnostic_pre", "retention_check"])
def test_expected_counts_present(kind):
    out = s._expected_counts(kind)
    assert isinstance(out, dict) and out


def test_validate_exam_counts_raises_on_mismatch():
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        s._validate_exam_counts("retention_check", [{"section": "EASY", "qtype": "mcq"}])


def test_llm_doc_summary_fallback(monkeypatch):
    monkeypatch.setattr(s, "llm_available", lambda: False)
    assert s._llm_doc_summary("abc") == "abc"
