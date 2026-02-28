from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Dict

from docx import Document


def export_assessment_to_docx(assessment: Dict[str, Any], *, kind: str = "") -> Path:
    """Export an assessment dict to a DOCX file and return its path."""
    fd, out_path = tempfile.mkstemp(prefix="assessment_", suffix=".docx")
    os.close(fd)

    doc = Document()
    doc.add_heading("ĐỀ KIỂM TRA", level=1)

    title = str(assessment.get("title") or "Assessment")
    level = str(assessment.get("level") or "")

    doc.add_paragraph(f"Tiêu đề: {title}")
    if kind:
        doc.add_paragraph(f"Loại: {kind}")
    if level:
        doc.add_paragraph(f"Mức độ: {level}")
    doc.add_paragraph("")

    questions = assessment.get("questions") or []
    for idx, q in enumerate(questions, start=1):
        qtype = str(q.get("type") or "").lower()
        bloom = str(q.get("bloom_level") or "")
        stem = str(q.get("stem") or "")

        p = doc.add_paragraph()
        p.add_run(f"Câu {idx} ({qtype.upper()})  Bloom: {bloom}\n").bold = True
        doc.add_paragraph(stem)

        if qtype == "mcq":
            opts = q.get("options") or []
            for oi, opt in enumerate(opts):
                label = chr(65 + oi)
                doc.add_paragraph(f"{label}. {opt}", style="List Bullet")
        elif qtype == "essay":
            mp = int(q.get("max_points") or 0)
            doc.add_paragraph(f"(Tự luận) Điểm tối đa: {mp}")

        doc.add_paragraph("")

    # Answer key
    doc.add_page_break()
    doc.add_heading("ĐÁP ÁN / HƯỚNG DẪN CHẤM", level=2)

    for idx, q in enumerate(questions, start=1):
        qtype = str(q.get("type") or "").lower()
        if qtype == "mcq":
            correct = q.get("correct_index")
            try:
                correct = int(correct)
                ans = chr(65 + correct)
            except Exception:
                ans = "?"
            doc.add_paragraph(f"Câu {idx}: {ans}")
        elif qtype == "essay":
            mp = int(q.get("max_points") or 0)
            doc.add_paragraph(f"Câu {idx}: chấm theo rubric (tối đa {mp} điểm)")
            rubric = q.get("rubric") or []
            for r in rubric[:6]:
                try:
                    desc = str(r.get("criteria") or r.get("name") or "")
                    pts = r.get("points")
                    doc.add_paragraph(f"- {desc}: {pts}")
                except Exception:
                    continue

    doc.save(out_path)
    return Path(out_path)
