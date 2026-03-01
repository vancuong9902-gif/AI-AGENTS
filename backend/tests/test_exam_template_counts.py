from __future__ import annotations

from app.services.exam_template_service import get_template, template_to_assessment_counts


def test_posttest_standard_template_counts_include_hard_mcq_bucket():
    template = get_template("posttest_standard")
    assert template is not None

    counts = template_to_assessment_counts(template)
    assert counts == {
        "easy_count": 0,
        "medium_count": 10,
        "hard_mcq_count": 6,
        "hard_count": 3,
    }
