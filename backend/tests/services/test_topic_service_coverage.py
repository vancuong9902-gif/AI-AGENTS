from __future__ import annotations

from app.services import topic_service as s


def test_topic_title_validation_and_cleaning():
    assert s.validate_topic_title("Intro") == "Intro"
    assert s.clean_topic_title("  1.2. Intro ")
    title, warnings = s.validate_and_clean_topic_title("Chapter 1: Intro")
    assert isinstance(title, str)
    assert isinstance(warnings, list)


def test_topic_text_classifiers():
    assert s.is_appendix_title("Phụ lục đáp án") is True
    assert s._is_mcq_choices_line("A. first") is True
    assert s._is_answer_key_line("Đáp án: A B C") is True
    assert s._is_practice_marker_line("Bài tập:") is True
    assert s._is_lesson_heading_line("Bài 3: vòng lặp") is True


def test_topic_similarity_and_normalization_helpers():
    assert s._jaccard({"a", "b"}, {"b", "c"}) > 0
    assert isinstance(s._title_token_set("Intro to Python"), set)
    assert isinstance(s._normalize_title_candidate("  CHƯƠNG 1: GIỚI THIỆU  "), str)
    assert isinstance(s._de_all_caps_title("INTRODUCTION TO PYTHON"), str)
    assert s._roman_to_int("XIV") == 14


def test_topic_content_processing_helpers():
    study, practice = s.split_study_and_practice("Theory\nBài tập:\n1. Câu hỏi")
    assert isinstance(study, str)
    assert isinstance(practice, str)
    cleaned = s.clean_text_for_generation("Lý thuyết\n\n\nĐáp án: A B C")
    assert isinstance(cleaned, str)
    assert isinstance(s.clean_topic_text_for_display("A. one\nB. two"), str)
    assert isinstance(s._clean_topic_body("abc\n\n\n"), str)


def test_topic_extraction_and_validation_smoke():
    chunks = ["1. Intro\nPython basics", "2. Loops\nfor and while"]
    extracted = s.extract_topics_from_headings(chunks)
    assert isinstance(extracted, list)
    post = s.post_process_generated_topics([{"title": "Intro", "body": "Body text"}], all_chunks=chunks)
    assert isinstance(post, list)
    assert isinstance(s.validate_and_repair_topics([{"title": "T", "body": "content" * 20, "start_chunk": 0, "end_chunk": 1}]), list)
    assert isinstance(s.validate_topic_quality([{"title": "T", "body": "content" * 20}]), list)
