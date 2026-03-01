from __future__ import annotations

from app.services import tutor_service


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, n):
        self._rows = self._rows[: int(n)]
        return self

    def all(self):
        return list(self._rows)


class _DB:
    def __init__(self):
        self.doc_rows = [("Giải tích 12",), ("Đại số nâng cao",)]
        self.topic_rows = [
            ("Đạo hàm", ["quy tắc", "hàm số"], "Khái niệm và quy tắc tính đạo hàm", 0.95),
            ("Ứng dụng đạo hàm", ["cực trị", "đơn điệu"], "Tìm cực trị và khảo sát hàm", 0.9),
            ("Tích phân", ["nguyên hàm"], "Khái niệm nguyên hàm cơ bản", 0.8),
        ]

    def query(self, *entities):
        cols = [getattr(e, "key", str(e)) for e in entities]
        if cols == ["title"]:
            return _Query(self.doc_rows)
        return _Query(self.topic_rows)


def _reset_gate_cache():
    tutor_service._OFFTOPIC_GATE_CACHE.clear()


def test_llm_gate_on_topic_dung_chuong(monkeypatch):
    _reset_gate_cache()
    monkeypatch.setattr(tutor_service, "llm_available", lambda: True)
    monkeypatch.setattr(
        tutor_service,
        "chat_json",
        lambda **_kwargs: {"is_on_topic": True, "reason": "Đúng nội dung chương đạo hàm", "matched_topic": "Đạo hàm"},
    )

    got = tutor_service._is_question_on_topic_llm(
        _DB(),
        "Trong chương đạo hàm, quy tắc đạo hàm tích là gì?",
        "Đạo hàm",
        [3, 1],
    )

    assert got == (True, "Đúng nội dung chương đạo hàm", "Đạo hàm")


def test_llm_gate_off_topic_giai_tri(monkeypatch):
    _reset_gate_cache()
    monkeypatch.setattr(tutor_service, "llm_available", lambda: True)
    monkeypatch.setattr(
        tutor_service,
        "chat_json",
        lambda **_kwargs: {"is_on_topic": False, "reason": "Câu hỏi giải trí ngoài phạm vi", "matched_topic": None},
    )

    is_on_topic, reason, matched = tutor_service._is_question_on_topic_llm(
        _DB(),
        "Phim nào đang hot nhất tuần này?",
        "Đạo hàm",
        [1, 2],
    )

    assert is_on_topic is False
    assert "ngoài phạm vi" in reason
    assert matched is None


def test_llm_gate_dien_dat_khac_van_on_topic(monkeypatch):
    _reset_gate_cache()
    monkeypatch.setattr(tutor_service, "llm_available", lambda: True)
    calls = {"count": 0}

    def _fake_chat_json(**_kwargs):
        calls["count"] += 1
        return {"is_on_topic": True, "reason": "Hỏi ứng dụng thực tế đúng tài liệu", "matched_topic": "Ứng dụng đạo hàm"}

    monkeypatch.setattr(tutor_service, "chat_json", _fake_chat_json)

    payload = (
        _DB(),
        "Nếu tối ưu chi phí sản xuất thì mình dùng kiến thức nào trong bài này?",
        "Đạo hàm",
        [2, 1],
    )
    got1 = tutor_service._is_question_on_topic_llm(*payload)
    got2 = tutor_service._is_question_on_topic_llm(*payload)

    assert got1[0] is True
    assert got2[0] is True
    assert got1[2] == "Ứng dụng đạo hàm"
    assert calls["count"] == 1
