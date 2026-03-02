from __future__ import annotations

from unittest.mock import patch

from app.services import quiz_service as s
from app.services import topic_service as ts


# ──────────────────── quiz_service: _snippet ──────────────────────────────────
def test_snippet_short_returns_unchanged():
    assert s._snippet("hello world") == "hello world"


def test_snippet_long_truncates_with_ellipsis():
    text = "word " * 30  # 150 chars
    result = s._snippet(text, max_len=20)
    assert result.endswith("…")
    assert len(result) <= 21


def test_snippet_empty():
    assert s._snippet("") == ""


def test_snippet_collapses_whitespace():
    assert s._snippet("a  b  c") == "a b c"


# ──────────────────── quiz_service: _is_codey ─────────────────────────────────
def test_is_codey_empty():
    assert s._is_codey("") is True


def test_is_codey_python_def():
    assert s._is_codey("def foo(): return x") is True


def test_is_codey_import():
    assert s._is_codey("import numpy as np") is True


def test_is_codey_console():
    assert s._is_codey("console.log('hello')") is True


def test_is_codey_high_symbols():
    assert s._is_codey("{};:=>{}<>**") is True


def test_is_codey_low_letters():
    assert s._is_codey("123 456 789") is True


def test_is_codey_normal_vi_text():
    assert s._is_codey("Đây là văn bản bình thường tiếng Việt") is False


def test_is_codey_normal_en_text():
    assert s._is_codey("This is a normal English sentence about learning") is False


def test_is_codey_numpy():
    assert s._is_codey("numpy arrays are fast") is True


def test_is_codey_equality():
    assert s._is_codey("x == y means equal comparison") is True


# ──────────────────── quiz_service: selected helpers ──────────────────────────
def test_pick_keyword_returns_string():
    sent = "Đệ quy là phương pháp gọi lại chính nó trong lập trình hiện đại."
    result = s._pick_keyword(sent, "lập trình")
    assert result is None or isinstance(result, str)


def test_mask_first_only_replaces_first():
    result = s._mask_first("Python loves Python deeply", "Python")
    assert result.count("Python") == 1
    assert "____" in result


def test_find_chunk_id_invalid_regex():
    chunks = [{"chunk_id": 1, "text": "hello"}]
    assert s._find_chunk_id(chunks, "[invalid regex") is None


def test_mcq_builds_valid_structure():
    q = s._mcq(
        stem="What is recursion?",
        correct="A function calling itself",
        wrongs=["A loop", "A class", "A variable"],
        chunk_id=5,
        explanation="Recursion means a function calls itself.",
    )
    assert q["type"] == "mcq"
    assert len(q["options"]) == 4
    assert q["correct_index"] == q["options"].index("A function calling itself")
    assert q["sources"] == [{"chunk_id": 5}]


def test_needs_standalone_rewrite_doc_ref():
    q = {"stem": "Theo tài liệu đã học, điều gì đúng nhất?", "options": [], "explanation": ""}
    assert s._needs_standalone_rewrite_mcq(q, []) is True


def test_needs_refine_good_question():
    q = {
        "stem": "Đệ quy là phương pháp giải quyết vấn đề bằng cách nào?",
        "options": ["Gọi lại chính nó", "Dùng vòng lặp for", "Dùng lớp kế thừa", "Dùng pointer trực tiếp"],
        "explanation": "Đệ quy là kỹ thuật lập trình mà hàm gọi lại chính nó để giải quyết bài toán nhỏ hơn.",
    }
    assert s._needs_refine([q]) is False


def test_clean_mcq_valid_question_passes():
    q = {
        "type": "mcq",
        "stem": "Phương pháp đệ quy được định nghĩa như thế nào trong lập trình?",
        "options": ["Hàm gọi lại chính nó", "Vòng lặp for", "Lớp kế thừa", "Biến toàn cục"],
        "correct_index": 0,
        "explanation": "Đệ quy là kỹ thuật hàm tự gọi lại chính nó.",
    }
    result = s.clean_mcq_questions([q])
    assert len(result) == 1


def test_generate_cloze_mcqs_empty_pool():
    chunks = [{"chunk_id": 0, "text": ""}]  # chunk_id=0 skipped
    result = s._generate_cloze_mcqs("topic", "beginner", 5, chunks, [])
    assert result == []


def test_enforce_standalone_cleans_doc_refs():
    with patch("app.services.quiz_service.llm_available", return_value=False):
        q = {"type": "mcq", "stem": "Theo tài liệu đã học, Python là gì?", "options": ["a", "b", "c", "d"], "correct_index": 0}
        result = s.enforce_standalone_mcqs(topic="Python", level="beginner", chunks=[], questions=[q])
        assert len(result) == 1
        assert "Theo tài liệu" not in result[0].get("stem", "")


# ──────────────────── topic_service: representative coverage ──────────────────
def test_jaccard_identical():
    assert ts._jaccard({"a", "b", "c"}, {"a", "b", "c"}) == 1.0


def test_merge_similar_topics_respects_max():
    topics = [
        {"title": f"Topic {i}", "body": f"Different body content number {i} about subject matter", "keywords": [f"topic{i}"]}
        for i in range(20)
    ]
    result = ts._merge_similar_topics(topics, max_topics=5)
    assert len(result) <= 5


def test_topic_confidence_no_llm():
    with patch("app.services.topic_service.llm_available", return_value=False):
        score = ts._topic_confidence_score("Introduction to Recursion", "Body with enough content" * 5)
        assert 0.0 <= score <= 1.0


def test_is_appendix_true():
    assert ts.is_appendix_title("Phụ lục đáp án") is True
    assert ts.is_appendix_title("appendix") is True


def test_clean_topic_title_short_raises():
    import pytest

    with pytest.raises(ValueError):
        ts.clean_topic_title("  ")


def test_split_study_and_practice_basic():
    text = "Study material here.\nBài tập:\n1. Question one?\n2. Question two?"
    study, practice = ts.split_study_and_practice(text)
    assert isinstance(study, str)
    assert isinstance(practice, str)


def test_extract_topics_from_headings_basic():
    chunks = [
        "1. Introduction\nThis is about introduction content and basics of the topic.",
        "2. Variables\nVariables are used to store data in programming.",
    ]
    result = ts.extract_topics_from_headings(chunks)
    assert isinstance(result, list)
