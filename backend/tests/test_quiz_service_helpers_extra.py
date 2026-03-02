from app.services import quiz_service as qs


def test_snippet_and_code_detection():
    assert qs._snippet("abc", max_len=10) == "abc"
    assert qs._snippet("a" * 50, max_len=10).endswith("…")
    assert qs._is_codey("def hello():\n    return 1") is True
    assert qs._is_codey("Đây là đoạn văn bản tự nhiên về toán học.") is False


def test_pick_keyword_mask_and_find_chunk_id():
    kw = qs._pick_keyword("Mô hình hồi quy tuyến tính học từ dữ liệu", "Mô hình")
    assert kw is not None
    masked = qs._mask_first("Hồi quy tuyến tính là phương pháp", "tuyến")
    assert "____" in masked
    cid = qs._find_chunk_id([{"chunk_id": "2", "text": "abc xyz"}], r"xyz")
    assert cid == 2
    assert qs._find_chunk_id([], "(") is None


def test_mcq_and_topic_stem_and_overlap_checks(monkeypatch):
    monkeypatch.setattr(qs.random, "shuffle", lambda arr: None)
    q = qs._mcq("Câu hỏi", "A", ["B", "C", "D"], 9, "giải thích", bloom_level="apply")
    assert q["correct_index"] == 0
    assert q["sources"] == [{"chunk_id": 9}]

    stem = qs._ensure_topic_in_stem("Nội dung chính là gì?", "Đại số")
    assert "Đại số" in stem

    assert qs._has_ngram_overlap_qs("một hai ba bốn năm sáu bảy", "không liên quan", n_words=3) is False
    assert qs._has_ngram_overlap_qs("một hai ba bốn", "zzz một hai ba yyy", n_words=3) is True


def test_needs_standalone_rewrite_detects_doc_reference():
    needs = qs._needs_standalone_rewrite_mcq(
        {"stem": "Theo tài liệu trên, kết luận nào đúng?"},
        [{"text": "random text"}],
    )
    assert needs is True
