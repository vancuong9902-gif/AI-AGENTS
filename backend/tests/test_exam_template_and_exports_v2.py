from __future__ import annotations

import pytest

from app.schemas.exam import ExamTemplateMetadata, ExamTemplateOut, ExamTemplateSection
from app.services.exam_template_service import template_to_assessment_counts
from app.services.exam_variant_service import _jaccard
from app.services.lms_report_export_service import export_report_pdf, export_report_xlsx


def test_template_difficulty_mapping_three_levels():
    tpl = ExamTemplateOut(
        template_id="t",
        name="T",
        kind="midterm",
        metadata=ExamTemplateMetadata(),
        sections=[
            ExamTemplateSection(type="multiple_choice", count=4, difficulty="easy"),
            ExamTemplateSection(type="multiple_choice", count=5, difficulty="medium"),
            ExamTemplateSection(type="multiple_choice", count=2, difficulty="hard"),
            ExamTemplateSection(type="essay", count=3, difficulty="hard"),
        ],
    )
    counts = template_to_assessment_counts(tpl)
    assert counts == {"easy_count": 4, "medium_count": 5, "hard_mcq_count": 2, "hard_count": 3}


def test_generate_variants_similarity_gate_math():
    a = {"q1", "q2", "q3"}
    b = {"q1", "q4", "q5"}
    sim = _jaccard(a, b)
    assert 0 < sim < 0.5


def test_export_excel_has_required_sheets_and_columns():
    pytest.importorskip("openpyxl")
    report = {
        "students": [
            {
                "student_id": 1,
                "name": "Nguyễn Văn A",
                "entry_score": 40,
                "mid_score": 60,
                "final_score": 80,
                "level": "intermediate",
                "topic_scores": {"Đại số": 75},
                "study_time_minutes": 120,
            }
        ],
        "summary": {"avg_improvement": 40},
    }
    path = export_report_xlsx(report, name="t")
    import openpyxl

    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == ["Gradebook", "TopicBreakdown", "StudyTime", "Summary"]
    headers = [c.value for c in wb["Gradebook"][1]]
    assert headers == ["student_id", "name", "pre", "mid", "post", "avg", "level"]


def test_export_pdf_unicode_vietnamese_font():
    report = {"students": [{"student_id": 1, "name": "Trần Thị B", "entry_score": 50, "final_score": 75, "level": "advanced", "study_time_minutes": 90}]}
    path = export_report_pdf(report, name="t")
    data = open(path, "rb").read()
    assert data.startswith(b"%PDF")
