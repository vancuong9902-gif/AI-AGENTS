import re

from app.services.topic_service import validate_topic_title

_BAD_CHARS = set("¸\u00ad¬×®¦§")
_READABLE_RX = re.compile(r"[A-Za-zÀ-ỹà-ỹ]{3,}")


def _assert_human_readable(text: str):
    assert text
    assert _READABLE_RX.search(text), text
    assert not any(ch in _BAD_CHARS for ch in text), text


def test_vni_times_encoded_title_is_repaired_to_readable_text():
    raw = "Ch­¬ng tr×nh häc m¸y c¬ b¶n"
    repaired = validate_topic_title(raw)
    _assert_human_readable(repaired)


def test_tcvn3_encoded_title_is_repaired_to_readable_text():
    raw = "Kü thuËt lËp tr×nh h­íng ®èi t­îng"
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
