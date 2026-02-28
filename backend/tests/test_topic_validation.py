from app.services.topic_service import validate_and_clean_topic_title, extract_topics


def test_validate_topic_title_tcvn3_encoding():
    raw = "Ph\xad¬ng tr×nh bËc hai"
    cleaned, warnings = validate_and_clean_topic_title(raw)
    assert "Phương trình" in cleaned
    assert any(w == "font_fixed" for w in warnings)


def test_validate_topic_title_vntime_encoding():
    raw = "N¨m häc vµ To¸n"
    cleaned, warnings = validate_and_clean_topic_title(raw)
    assert "Năm học" in cleaned
    assert "font_fixed" in warnings


def test_validate_topic_title_english_ok():
    cleaned, warnings = validate_and_clean_topic_title("Linear Algebra and Matrices")
    assert cleaned == "Linear Algebra and Matrices"
    assert warnings == []


def test_extract_topics_low_text_table_heavy_marks_reviewable():
    full_text = """
    Chương 1: Bảng số liệu
    | STT | Giá trị | Ghi chú |
    | 1 | 10 | A |
    | 2 | 15 | B |

    Chương 2: Hình ảnh minh họa
    Hình 1.1
    Hình 1.2
    """
    obj = extract_topics(full_text, heading_level="chapter", include_details=False, max_topics=10)
    assert obj.get("status") == "OK"
    topics = obj.get("topics") or []
    assert topics
    assert all("extraction_confidence" in t for t in topics)
    assert any(bool(t.get("needs_review")) for t in topics)
