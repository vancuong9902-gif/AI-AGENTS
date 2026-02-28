import unicodedata

from app.services.topic_service import extract_topics

_BAD_CHARS = set("¸\u00ad¬×®¦§©")


def _is_unicode_vn_normalized(s: str) -> bool:
    return s == unicodedata.normalize("NFC", s)


def test_extract_topics_handles_tcvn3_broken_heading_font():
    full_text = (
        "Ch\u00ad¬ng 1: H\u00e0m s\u1ed1 v\u00e0 \u1ee9ng d\u1ee5ng\n"
        + "H\u00e0m s\u1ed1 m\u00f4 t\u1ea3 m\u1ed1i li\u00ean h\u1ec7 gi\u1eefa \u0111\u1ea7u v\u00e0o v\u00e0 \u0111\u1ea7u ra. " * 30
        + "\nCh\u00ad¬ng 2: \u0110\u1ea1o h\u00e0m c\u01a1 b\u1ea3n\n"
        + "\u0110\u1ea1o h\u00e0m cho bi\u1ebft t\u1ed1c \u0111\u1ed9 thay \u0111\u1ed5i c\u1ee7a h\u00e0m s\u1ed1 theo bi\u1ebfn. " * 30
    )

    resp = extract_topics(full_text, heading_level="chapter", include_details=False, max_topics=8)
    topics = resp.get("topics") or []

    assert resp.get("status") == "OK"
    assert topics

    for topic in topics:
        title = str(topic.get("title") or "")
        assert title
        assert _is_unicode_vn_normalized(title)
        assert not any(ch in _BAD_CHARS for ch in title)
