from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
import zipfile

from app.services import exam_docx_service


def test_generate_exam_docx_zip_contains_variants_and_answer_key(monkeypatch):
    monkeypatch.setattr(exam_docx_service, "_topic_names", lambda db, topic_ids: ["Đại số"])
    pool = [
        SimpleNamespace(id=i, stem=f"Câu hỏi {i} Đại số", options=["A", "B", "C", "D"], correct_index=i % 4)
        for i in range(1, 120)
    ]
    monkeypatch.setattr(exam_docx_service, "_question_bank", lambda db, topic_names, limit=400: pool)

    blob = exam_docx_service.generate_exam_docx_zip(
        db=None,
        classroom_id=1,
        topic_ids=[1],
        num_variants=3,
        questions_per_exam=20,
        exam_type="multiple_choice",
        difficulty_distribution={"easy": 30, "medium": 50, "hard": 20},
        include_answer_key=True,
        exam_title="Kiểm tra Chương 1",
        school_name="Trường THPT ABC",
        subject="Toán",
    )

    with zipfile.ZipFile(BytesIO(blob), "r") as zf:
        names = sorted(zf.namelist())
    assert "dap_an.docx" in names
    assert "de_001.docx" in names
    assert "de_002.docx" in names
    assert "de_003.docx" in names
