from __future__ import annotations

from app.services import tutor_service


def test_llm_gate_out_of_scope(monkeypatch):
    monkeypatch.setattr(tutor_service.settings, "TUTOR_LLM_OFFTOPIC_ENABLED", True)
    monkeypatch.setattr(tutor_service, "llm_available", lambda: True)
    monkeypatch.setattr(
        tutor_service,
        "chat_json",
        lambda **_kwargs: {"status": "out_of_scope", "confidence": 0.93, "reason": "khong_lien_quan_tai_lieu"},
    )

    got = tutor_service._llm_offtopic_gate(
        question="Ai vô địch World Cup 2022?",
        topic="Hàm bậc hai",
        evidence_previews=["Định nghĩa hàm số bậc hai", "Đồ thị parabol"],
    )

    assert got["status"] == "out_of_scope"
    assert got["confidence"] == 0.93


def test_llm_gate_in_scope(monkeypatch):
    monkeypatch.setattr(tutor_service.settings, "TUTOR_LLM_OFFTOPIC_ENABLED", True)
    monkeypatch.setattr(tutor_service, "llm_available", lambda: True)
    monkeypatch.setattr(
        tutor_service,
        "chat_json",
        lambda **_kwargs: {"status": "in_scope", "confidence": 0.88, "reason": "trung_khop_evidence"},
    )

    got = tutor_service._llm_offtopic_gate(
        question="Công thức nghiệm của phương trình bậc hai là gì?",
        topic="Phương trình bậc hai",
        evidence_previews=["Công thức nghiệm", "Biệt thức delta"],
    )

    assert got["status"] == "in_scope"
    assert got["confidence"] == 0.88


def test_llm_gate_uncertain(monkeypatch):
    monkeypatch.setattr(tutor_service.settings, "TUTOR_LLM_OFFTOPIC_ENABLED", True)
    monkeypatch.setattr(tutor_service, "llm_available", lambda: True)
    monkeypatch.setattr(
        tutor_service,
        "chat_json",
        lambda **_kwargs: {"status": "uncertain", "confidence": 0.41, "reason": "cau_hoi_mo_ho"},
    )

    got = tutor_service._llm_offtopic_gate(
        question="Giải thích cái này giúp mình",
        topic="Điện xoay chiều",
        evidence_previews=["Mạch RLC", "Độ lệch pha"],
    )

    assert got["status"] == "uncertain"
    assert got["confidence"] == 0.41


def test_llm_gate_disabled_falls_back_to_in_scope(monkeypatch):
    monkeypatch.setattr(tutor_service.settings, "TUTOR_LLM_OFFTOPIC_ENABLED", False)
    monkeypatch.setattr(tutor_service, "llm_available", lambda: True)

    got = tutor_service._llm_offtopic_gate(
        question="Ai vô địch World Cup 2022?",
        topic="Hàm bậc hai",
        evidence_previews=["Định nghĩa hàm số bậc hai"],
    )

    assert got["status"] == "in_scope"
    assert got["reason"] == "gate_disabled"
