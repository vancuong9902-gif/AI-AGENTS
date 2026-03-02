from __future__ import annotations

from app.services import quiz_service as s


def test_quiz_service_helpers_smoke():
    assert s._snippet("hello") == "hello"
    assert s._is_codey("def foo():\n  return 1") is True
    assert s._mask_first("Python is great", "Python").startswith("___")
    assert s._normalize_ws_qs("  a   b  ") == "a b"
    sanitized = s._sanitize_options(["a", "", None, "a", "b"])
    assert isinstance(sanitized, list)
    assert "a" in sanitized and "b" in sanitized


def test_quiz_service_extraction_helpers():
    chunks = [{"chunk_id": 1, "text": "Đệ quy là kỹ thuật hàm tự gọi chính nó."}]
    assert isinstance(s._mine_definitions(chunks), list)
    assert s._split_items("x\ny") == ["x y"]
    assert s._term_ok("recursion") is True
    assert s._term_ok("12") is False


def test_quiz_generation_helpers_and_cleanup():
    chunks = [{"chunk_id": 2, "text": "Python supports list comprehension and generators."}]
    assert isinstance(s._extract_term_pool(chunks, max_terms=10), list)
    assert isinstance(s._build_sentence_pool("python", chunks), list)
    distractors = s._pick_distractors("python", ["java", "c++", "go", "rust"], k=3)
    assert 1 <= len(distractors) <= 3

    cleaned = s.clean_mcq_questions(
        [
            {"stem": "What is Python?", "options": ["lang", "lang", "snake", "tool"], "answer": "lang", "qtype": "mcq"},
            {"stem": "What is Python?", "options": ["lang", "lang", "snake", "tool"], "answer": "lang", "qtype": "mcq"},
        ],
        limit=1,
    )
    assert isinstance(cleaned, list)


def test_quiz_practice_level_helpers():
    assert isinstance(s._practice_bloom_targets("beginner"), list)
    assert isinstance(s._practice_level_to_generator_level("advanced"), str)
    assert isinstance(s._quiz_refine_enabled(), bool)
