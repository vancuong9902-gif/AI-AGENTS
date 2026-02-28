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
