from __future__ import annotations

import os
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_DEJAVU_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_DEJAVU_BOLD_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


_font_registered = False


def _register_fonts() -> tuple[str, str]:
    global _font_registered
    if not _font_registered and os.path.exists(_DEJAVU_FONT_PATH):
        pdfmetrics.registerFont(TTFont("DejaVu", _DEJAVU_FONT_PATH))
        if os.path.exists(_DEJAVU_BOLD_FONT_PATH):
            pdfmetrics.registerFont(TTFont("DejaVu-Bold", _DEJAVU_BOLD_FONT_PATH))
        _font_registered = True

    if _font_registered:
        return "DejaVu", "DejaVu-Bold"
    return "Helvetica", "Helvetica-Bold"


def generate_class_report_pdf(classroom_data: dict[str, Any], students_data: list[dict[str, Any]]) -> bytes:
    base_font, bold_font = _register_fonts()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()

    _ = ParagraphStyle("Vietnamese", parent=styles["Normal"], fontName=base_font, fontSize=10)
    title_style = ParagraphStyle(
        "TitleVietnamese",
        parent=styles["Title"],
        fontName=bold_font,
        fontSize=16,
        alignment=1,
    )

    elements: list[Any] = []
    elements.append(Paragraph(f'BÁO CÁO LỚP HỌC: {classroom_data.get("name", "N/A")}', title_style))
    elements.append(Spacer(1, 20))

    table_data = [["STT", "Họ tên", "Điểm đầu vào", "Điểm cuối kỳ", "Xếp loại"]]
    for i, student in enumerate(students_data, 1):
        table_data.append(
            [
                i,
                str(student.get("name") or "N/A"),
                float(student.get("placement_score") or 0.0),
                float(student.get("final_score") or 0.0),
                str(student.get("level") or "N/A").upper(),
            ]
        )

    table = Table(table_data, colWidths=[35, 200, 85, 85, 85])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4A90D9")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), bold_font),
                ("FONTNAME", (0, 1), (-1, -1), base_font),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (2, 1), (3, -1), "CENTER"),
                ("ALIGN", (4, 1), (4, -1), "CENTER"),
            ]
        )
    )
    elements.append(table)

    doc.build(elements)
    return buffer.getvalue()
