from __future__ import annotations

import hashlib

import pytest
from fastapi import HTTPException

from app.services import agent_service


def _fp(stem: str) -> str:
    norm = " ".join(stem.lower().replace("?", "").split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def test_generate_diagnostic_pre_payload_respects_counts_and_time(monkeypatch):
    evidence = [
        {"chunk_id": 11, "text": "Topic A basics", "meta": {"page": 2}},
        {"chunk_id": 12, "text": "Topic B advanced", "meta": {"page": 3}},
    ]

    excluded = _fp("Câu easy bị loại?")

    def fake_chat_json(*args, **kwargs):
        return {
            "questions": [
                {
                    "type": "mcq",
                    "stem": "Câu easy bị loại?",
                    "options": ["A", "B", "C", "D"],
                    "correct_index": 0,
                    "explanation": "exp",
                    "bloom_level": "remember",
                    "difficulty": "easy",
                    "topic": "Topic A",
                    "sources": [{"chunk_id": 11, "page": 2}],
                    "estimated_minutes": 2,
                },
                {
                    "type": "mcq",
                    "stem": "Câu easy hợp lệ",
                    "options": ["A", "B", "C", "D"],
                    "correct_index": 1,
                    "explanation": "exp",
                    "bloom_level": "understand",
                    "difficulty": "easy",
                    "topic": "Topic A",
                    "sources": [{"chunk_id": 11, "page": 2}],
                    "estimated_minutes": 2,
                },
                {
                    "type": "mcq",
                    "stem": "Câu medium hợp lệ",
                    "options": ["A", "B", "C", "D"],
                    "correct_index": 2,
                    "explanation": "exp",
                    "bloom_level": "apply",
                    "difficulty": "medium",
                    "topic": "Topic B",
                    "sources": [{"chunk_id": 12, "page": 3}],
                    "estimated_minutes": 3,
                },
                {
                    "type": "essay",
                    "stem": "Câu hard tự luận hợp lệ",
                    "expected_answer": "Ý chính",
                    "rubric": [{"criterion": "đúng ý", "points": 5}],
                    "explanation": "exp",
                    "bloom_level": "analyze",
                    "difficulty": "hard",
                    "topic": "Topic B",
                    "sources": [{"chunk_id": 12, "page": 3}],
                    "estimated_minutes": 5,
                },
            ]
        }

    monkeypatch.setattr(agent_service, "chat_json", fake_chat_json)

    out = agent_service.generate_diagnostic_pre_payload(
        selected_topics=["Topic A", "Topic B"],
        evidence_chunks=evidence,
        config={"easy_count": 1, "medium_count": 1, "hard_count": 1},
        time_policy="timed",
        duration_seconds=420,
        exclude_history=[excluded],
    )

    assert out["kind"] == "diagnostic_pre"
    assert len(out["questions"]) == 3
    assert [q["difficulty"] for q in out["questions"]] == ["easy", "medium", "hard"]
    assert out["time_limit_minutes"] == 7


def test_generate_diagnostic_pre_payload_requires_hard_essay(monkeypatch):
    evidence = [{"chunk_id": 11, "text": "Topic A basics"}]

    def fake_chat_json(*args, **kwargs):
        return {
            "questions": [
                {
                    "type": "mcq",
                    "stem": "Câu hard nhưng trắc nghiệm",
                    "options": ["A", "B", "C", "D"],
                    "correct_index": 0,
                    "explanation": "exp",
                    "bloom_level": "analyze",
                    "difficulty": "hard",
                    "topic": "Topic A",
                    "sources": [{"chunk_id": 11}],
                    "estimated_minutes": 5,
                }
            ]
        }

    monkeypatch.setattr(agent_service, "chat_json", fake_chat_json)

    with pytest.raises(HTTPException) as exc:
        agent_service.generate_diagnostic_pre_payload(
            selected_topics=["Topic A"],
            evidence_chunks=evidence,
            config={"easy_count": 0, "medium_count": 0, "hard_count": 1},
            time_policy="timed",
            duration_seconds=600,
            exclude_history=[],
        )

    assert exc.value.status_code == 422
    assert "requires essay" in str(exc.value.detail)
