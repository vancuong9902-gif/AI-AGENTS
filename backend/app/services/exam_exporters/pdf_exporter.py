from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Dict

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


def _register_vi_font() -> str:
    """Register a TTF font that supports Vietnamese Unicode.

    We try system DejaVu Sans first. If not available, we fall back to Helvetica.
    """
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            font_name = "DejaVuSans"
            try:
                pdfmetrics.registerFont(TTFont(font_name, p))
                return font_name
            except Exception:
                continue
    return "Helvetica"


def export_assessment_to_pdf(assessment: Dict[str, Any], *, kind: str = "") -> Path:
    """Export an assessment dict to a PDF file and return its path."""
    font = _register_vi_font()
    fd, out_path = tempfile.mkstemp(prefix="assessment_", suffix=".pdf")
    os.close(fd)

    c = canvas.Canvas(out_path, pagesize=A4)
    width, height = A4
    margin_x = 18 * mm
    y = height - 18 * mm

    def line(text: str, size: int = 11, leading: int = 14):
        nonlocal y
        c.setFont(font, size)
        c.drawString(margin_x, y, text)
        y -= leading
        if y < 20 * mm:
            c.showPage()
            y = height - 18 * mm

    title = str(assessment.get("title") or "Assessment")
    level = str(assessment.get("level") or "")

    line("ĐỀ KIỂM TRA", 16, 20)
    line(f"Tiêu đề: {title}", 12, 16)
    if kind:
        line(f"Loại: {kind}", 11, 14)
    if level:
        line(f"Mức độ: {level}", 11, 14)
    line(" ")

    questions = assessment.get("questions") or []
    for idx, q in enumerate(questions, start=1):
        qtype = str(q.get("type") or "").lower()
        bloom = str(q.get("bloom_level") or "")
        stem = str(q.get("stem") or "")

        line(f"Câu {idx} ({qtype.upper()})  Bloom: {bloom}", 11, 14)
        # simple wrapping: split on approx length
        for chunk in _wrap_text(stem, 95):
            line(chunk, 11, 14)

        if qtype == "mcq":
            opts = q.get("options") or []
            for oi, opt in enumerate(opts):
                label = chr(65 + oi)
                for chunk in _wrap_text(f"{label}. {opt}", 92):
                    line("   " + chunk, 11, 14)
        elif qtype == "essay":
            mp = int(q.get("max_points") or 0)
            line(f"(Tự luận) Điểm tối đa: {mp}")
        line(" ")

    # Answer key
    c.showPage()
    y = height - 18 * mm
    line("ĐÁP ÁN / HƯỚNG DẪN CHẤM", 14, 18)
    line(" ")
    for idx, q in enumerate(questions, start=1):
        qtype = str(q.get("type") or "").lower()
        if qtype == "mcq":
            correct = q.get("correct_index")
            try:
                correct = int(correct)
                ans = chr(65 + correct)
            except Exception:
                ans = "?"
            line(f"Câu {idx}: {ans}")
        elif qtype == "essay":
            mp = int(q.get("max_points") or 0)
            line(f"Câu {idx}: chấm theo rubric (tối đa {mp} điểm)")
            rubric = q.get("rubric") or []
            for r in rubric[:6]:
                try:
                    desc = str(r.get("criteria") or r.get("name") or "")
                    pts = r.get("points")
                    line(f"   - {desc}: {pts}")
                except Exception:
                    continue

    c.save()
    return Path(out_path)


def _wrap_text(text: str, max_len: int) -> list[str]:
    """Very small wrap helper for reportlab drawString."""
    text = (text or "").strip()
    if len(text) <= max_len:
        return [text] if text else []
    words = text.split()
    lines: list[str] = []
    cur: list[str] = []
    for w in words:
        if sum(len(x) for x in cur) + len(cur) + len(w) <= max_len:
            cur.append(w)
        else:
            if cur:
                lines.append(" ".join(cur))
            cur = [w]
    if cur:
        lines.append(" ".join(cur))
    return lines
