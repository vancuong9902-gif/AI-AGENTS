import re

from app.services.topic_service import post_process_generated_topics, validate_topic_title
from app.services.vietnamese_font_fix import fix_mojibake_topic

_BAD_CHARS = set("¸\u00ad¬×®¦§")
_READABLE_RX = re.compile(r"[A-Za-zÀ-ỹà-ỹ]{3,}")


def _assert_human_readable(text: str):
    assert text
    assert _READABLE_RX.search(text), text
    assert not any(ch in _BAD_CHARS for ch in text), text


def test_vni_times_encoded_title_is_repaired_to_readable_text():
    raw = "Ch\u00ad¬ng tr×nh häc m¸y c¬ b¶n"
    repaired = validate_topic_title(raw)
    _assert_human_readable(repaired)


def test_tcvn3_encoded_title_is_repaired_to_readable_text():
    raw = "Kü thuËt lËp tr×nh h\u00adíng ®èi t\u00adîng"
    repaired = validate_topic_title(raw)
    _assert_human_readable(repaired)


def test_symbol_wingdings_noise_is_repaired_to_readable_text():
    raw = "To¸n rêi r¹c ¦ § và øng dông"
    repaired = validate_topic_title(raw)
    _assert_human_readable(repaired)


def test_clean_unicode_utf8_title_keeps_original_content():
    title = "Giải tích đa biến và ứng dụng"
    repaired = validate_topic_title(title)
    assert repaired == title
    _assert_human_readable(repaired)


def test_vni_typing_heading_is_repaired_to_unicode_title():
    raw = "Toa1n ho5c lo7p 10"
    repaired = validate_topic_title(raw)
    assert repaired == "Toán học lớp 10"
    _assert_human_readable(repaired)


def test_fix_mojibake_topic_returns_utf8_vietnamese():
    assert fix_mojibake_topic("PhÆ°Æ¡ng trÃ¬nh báº­c hai") == "Phương trình bậc hai"


def test_extract_topics_repair_mojibake_vietnamese_title():
    raw_topics = [
        {
            "title": "1) PhÆ°Æ¡ng trÃ¬nh báº­c hai",
            "summary": "Giới thiệu dạng phương trình bậc hai và cách giải.",
            "keywords": ["phương trình", "bậc hai"],
        }
    ]
    chunks = [
        "Phương trình bậc hai xuất hiện trong đại số phổ thông.",
        "Các phương pháp giải phương trình bậc hai được trình bày chi tiết.",
    ]

    topics = post_process_generated_topics(raw_topics, chunks)
    assert topics
    assert topics[0]["title"] == "Phương trình bậc hai"


def test_extract_topics_english_pdf_returns_clean_english_topic():
    raw_topics = [
        {
            "title": "1. Quadratic equations",
            "summary": "Discusses discriminant and roots in algebra.",
            "keywords": ["quadratic", "equations", "roots"],
        }
    ]
    chunks = [
        "Quadratic equations appear in algebra and physics.",
        "Roots of quadratic equations are computed using the discriminant.",
    ]

    topics = post_process_generated_topics(raw_topics, chunks)
    assert topics
    assert topics[0]["title"] == "Quadratic equations"


def test_extract_topics_mixed_language_keeps_language_specific_titles():
    raw_topics = [
        {
            "title": "Chương 1: Hệ phương trình tuyến tính",
            "summary": "Nội dung tiếng Việt về hệ phương trình.",
            "keywords": ["hệ phương trình", "tuyến tính"],
        },
        {
            "title": "2) Vector dot product",
            "summary": "English explanation of vector operations.",
            "keywords": ["vector", "dot product"],
        },
    ]
    chunks = [
        "Bài học về hệ phương trình tuyến tính và phương pháp khử Gauss.",
        "Ví dụ hệ phương trình tuyến tính trong thực tế.",
        "Vector dot product is used to compute projection.",
        "Applications of vector dot product in geometry.",
    ]

    topics = post_process_generated_topics(raw_topics, chunks)
    titles = [t["title"] for t in topics]
    assert "Hệ phương trình tuyến tính" in titles
    assert "Vector dot product" in titles
