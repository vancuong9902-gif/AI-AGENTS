from __future__ import annotations

import os
import tempfile
import zipfile
import json
from pathlib import Path
from typing import Any, Dict, List

from docx import Document
from docx.oxml.ns import qn


def _set_times_new_roman(doc: Document) -> None:
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style._element.rPr.rFonts.set(qn("w:ascii"), "Times New Roman")
    style._element.rPr.rFonts.set(qn("w:hAnsi"), "Times New Roman")
    style._element.rPr.rFonts.set(qn("w:cs"), "Times New Roman")


def export_assessment_to_docx(assessment: Dict[str, Any], *, kind: str = "") -> Path:
    """Export an assessment dict to a DOCX file and return its path."""
    fd, out_path = tempfile.mkstemp(prefix="assessment_", suffix=".docx")
    os.close(fd)

    doc = Document()
    _set_times_new_roman(doc)
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


def export_multi_variant_docx(*, variants: List[Dict[str, Any]], title: str = "Bộ đề") -> Path:
    fd, out_path = tempfile.mkstemp(prefix="assessment_multi_", suffix=".docx")
    os.close(fd)

    doc = Document()
    _set_times_new_roman(doc)
    doc.add_heading(str(title or "Bộ đề"), level=1)

    for idx, variant in enumerate(variants, start=1):
        code = str(variant.get("paper_code") or f"{idx:02d}")
        doc.add_heading(f"Đề {code}", level=2)
        for q_idx, q in enumerate((variant.get("questions") or []), start=1):
            stem = str(q.get("stem") or "")
            qtype = str(q.get("type") or "").lower()
            doc.add_paragraph(f"Câu {q_idx} ({qtype.upper()}): {stem}")
            if qtype == "mcq":
                for oi, opt in enumerate((q.get("options") or []), start=0):
                    doc.add_paragraph(f"{chr(65 + oi)}. {opt}", style="List Bullet")
        if idx < len(variants):
            doc.add_page_break()

    doc.add_page_break()
    doc.add_heading("Đáp án tổng hợp", level=2)
    for idx, variant in enumerate(variants, start=1):
        code = str(variant.get("paper_code") or f"{idx:02d}")
        doc.add_heading(f"Đề {code}", level=3)
        for q_idx, q in enumerate((variant.get("questions") or []), start=1):
            if str(q.get("type") or "").lower() == "mcq":
                try:
                    answer = chr(65 + int(q.get("correct_index")))
                except Exception:
                    answer = "?"
                doc.add_paragraph(f"Câu {q_idx}: {answer}")
            else:
                doc.add_paragraph(f"Câu {q_idx}: Tự luận")

    doc.save(out_path)
    return Path(out_path)


def export_batch_to_zip(papers: List[Dict[str, Any]], include_answer_key: bool) -> Path:
    base_dir = Path(tempfile.mkdtemp(prefix="batch_exam_"))
    zip_path = base_dir / "batch_exam.zip"

    metadata = {
        "total_papers": len(papers),
        "codes": [str(p.get("paper_code") or "") for p in papers],
    }

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for idx, paper in enumerate(papers, start=1):
            code = str(paper.get("paper_code") or f"P{idx}")
            docx_path = export_assessment_to_docx(paper)
            zf.write(docx_path, arcname=f"paper_{code}.docx")

        if include_answer_key:
            key_doc = Document()
            key_doc.add_heading("BẢNG ĐÁP ÁN", level=1)
            for paper in papers:
                code = str(paper.get("paper_code") or "?")
                key_doc.add_heading(f"Đề {code}", level=2)
                questions = paper.get("questions") or []
                for qi, q in enumerate(questions, start=1):
                    qtype = str(q.get("type") or "").lower()
                    if qtype == "mcq":
                        try:
                            ans = chr(65 + int(q.get("correct_index")))
                        except Exception:
                            ans = "?"
                        key_doc.add_paragraph(f"Q{qi}: {ans}")
                    else:
                        key_doc.add_paragraph(f"Q{qi}: Essay")

            answer_key_path = base_dir / "answer_key.docx"
            key_doc.save(answer_key_path)
            zf.write(answer_key_path, arcname="answer_key.docx")

        metadata_path = base_dir / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        zf.write(metadata_path, arcname="metadata.json")

    return zip_path
