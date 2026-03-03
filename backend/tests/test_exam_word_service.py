from __future__ import annotations

import io
import zipfile

from app.services.exam_word_service import generate_exam_word


def test_generate_exam_word_single_version_returns_docx():
    content, filename = generate_exam_word(
        [
            {
                "question_text": "2 + 2 = ?",
                "type": "multiple_choice",
                "options": ["1", "2", "3", "4"],
                "correct_answer": "4",
            }
        ],
        num_versions=1,
        include_answer_key=True,
    )
    assert filename == "exam.docx"
    assert content.startswith(b"PK")


def test_generate_exam_word_multi_version_returns_zip():
    content, filename = generate_exam_word(
        [
            {
                "question_text": "Nêu định nghĩa đạo hàm",
                "type": "essay",
                "options": [],
                "correct_answer": "",
            }
        ],
        num_versions=2,
        include_answer_key=False,
    )
    assert filename == "de_thi.zip"
    with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
        names = sorted(zf.namelist())
    assert names == ["de_thi_so_1.docx", "de_thi_so_2.docx"]
