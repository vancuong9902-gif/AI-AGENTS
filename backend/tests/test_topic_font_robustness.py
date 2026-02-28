import re
import unicodedata

from app.services.topic_service import extract_topics

_BAD_CHARS = set("¸\u00ad¬×®¦§")
_ALLOWED_TITLE_RX = re.compile(r"^[\u0020-\u007E\u00C0-\u024F\u1E00-\u1EFF]+$")


def _is_unicode_vn_normalized(s: str) -> bool:
    return s == unicodedata.normalize("NFC", s)


def test_extract_topics_handles_tcvn3_broken_heading_font():
    full_text = (
        "Ch\u00ad¬ng 1 §¹i sè t\u00ad tuy Õn\n"
        + "Đại số tuyến tính nghiên cứu vector, ma trận và các phép biến đổi tuyến tính. " * 35
        + "\nKết luận\n"
        + "Tổng kết nội dung đại số tuyến tính, nhấn mạnh ứng dụng của vector và ma trận trong mô hình hóa. " * 45
    )

    resp = extract_topics(full_text, heading_level="chapter", include_details=False, max_topics=8)
    result = resp.get("topics") or []

    assert resp.get("status") == "OK"
    assert len(result) > 0

    for topic in result:
        title = str(topic.get("title") or "")
        assert title
        assert _is_unicode_vn_normalized(title)
        assert not any(ch in _BAD_CHARS for ch in title)
        assert _ALLOWED_TITLE_RX.fullmatch(title), title
