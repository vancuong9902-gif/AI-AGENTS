from app.services.topic_material_service import validate_material_payload


def _payload_ok():
    return {
        "theory": {"summary": "S", "key_concepts": ["A"], "content_md": "# C"},
        "exercises": {
            "easy": [{"question": "Q1", "type": "mcq", "options": ["A", "B", "C", "D"], "answer": "A", "explanation": "E", "source_chunks": [10]}],
            "medium": [{"question": "Q2", "type": "short", "answer": "Ans", "explanation": "Ex", "source_chunks": [11]}],
            "hard": [{"question": "Q3", "type": "essay", "answer": "Ans", "explanation": "Ex", "source_chunks": [12]}],
        },
        "mini_quiz": [
            {"question": "M1", "type": "mcq", "options": ["A", "B", "C", "D"], "answer": "A", "explanation": "E", "source_chunks": [10]},
            {"question": "M2", "type": "mcq", "options": ["A", "B", "C", "D"], "answer": "A", "explanation": "E", "source_chunks": [11]},
            {"question": "M3", "type": "mcq", "options": ["A", "B", "C", "D"], "answer": "A", "explanation": "E", "source_chunks": [12]},
            {"question": "M4", "type": "mcq", "options": ["A", "B", "C", "D"], "answer": "A", "explanation": "E", "source_chunks": [10]},
            {"question": "M5", "type": "mcq", "options": ["A", "B", "C", "D"], "answer": "A", "explanation": "E", "source_chunks": [11]},
        ],
    }


def test_validate_material_payload_ok():
    ok, errs, normalized = validate_material_payload(_payload_ok(), [10, 11, 12])
    assert ok is True
    assert errs == []
    assert len(normalized["mini_quiz"]) == 5


def test_validate_material_payload_rejects_unknown_chunk_ids():
    payload = _payload_ok()
    payload["exercises"]["easy"][0]["source_chunks"] = [999]
    ok, errs, _ = validate_material_payload(payload, [10, 11, 12])
    assert ok is False
    assert "exercise_easy_invalid_source_chunks" in errs


def test_validate_material_payload_requires_non_empty_source_chunks():
    payload = _payload_ok()
    payload["mini_quiz"][0]["source_chunks"] = []
    ok, errs, _ = validate_material_payload(payload, [10, 11, 12])
    assert ok is False
    assert "quiz_missing_source_chunks" in errs
