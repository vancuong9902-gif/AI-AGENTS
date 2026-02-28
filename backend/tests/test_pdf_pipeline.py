from app.services.document_pipeline import _pick_best_pdf_extraction
from app.api.routes.documents import _dynamic_topic_target


def test_pick_best_pdf_extraction_prefers_coverage_over_quality():
    high_quality_low_cov = (
        "hq_low_cov",
        "Đây là văn bản sạch. " * 100,
        [{"text": "x", "meta": {"page": 1}} for _ in range(10)],
    )
    med_quality_full_cov = (
        "mid_full_cov",
        ("đây là nội dung sách dài và đầy đủ hơn. " * 250),
        [{"text": "x", "meta": {"page": p}} for p in range(1, 11)],
    )

    picked = _pick_best_pdf_extraction([high_quality_low_cov, med_quality_full_cov], total_pages=10)
    assert picked is not None
    _, _, report = picked
    assert report["chosen_extractor"] == "mid_full_cov"


def test_dynamic_topic_target_scales_for_long_document():
    short_target = _dynamic_topic_target("abc " * 500)
    long_target = _dynamic_topic_target("abc " * 80000)
    assert short_target >= 12
    assert long_target > short_target
    assert long_target >= 25


from app.services.topic_service import _extract_by_chapters


def test_topic_split_stability_non_empty():
    chapter1 = "Chương 1: Hàm số\n" + "Hàm số biểu diễn mối quan hệ giữa biến đầu vào và đầu ra. " * 40
    chapter2 = "Chương 2: Vòng lặp\n" + "Vòng lặp for/while giúp lặp thao tác với dữ liệu có quy luật. " * 40
    chapter3 = "Chương 3: Danh sách\n" + "Danh sách cho phép lưu tập phần tử và thao tác bằng slicing, append. " * 40
    text = f"{chapter1}\n\n{chapter2}\n\n{chapter3}"
    chunks = [{"text": x, "meta": {}} for x in text.split("\n\n") if x.strip()]
    topics = _extract_by_chapters(text)
    assert topics
    assert len(topics) >= 2
    assert all(str(t.get("title") or "").strip() for t in topics)
