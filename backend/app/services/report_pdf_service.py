from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.models.attempt import Attempt
from app.models.classroom import Classroom, ClassroomMember
from app.models.classroom_assessment import ClassroomAssessment
from app.models.learner_profile import LearnerProfile
from app.models.quiz_set import QuizSet
from app.models.user import User
from app.services.lms_service import (
    analyze_topic_weak_points,
    build_recommendations,
    generate_full_teacher_report,
    score_breakdown,
)

_DEJAVU_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _register_font() -> str:
    if os.path.exists(_DEJAVU_PATH):
        try:
            pdfmetrics.registerFont(TTFont("DejaVuSans", _DEJAVU_PATH))
            return "DejaVuSans"
        except Exception:
            pass
    return "Helvetica"


def _build_styles(font_name: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title_vn", parent=base["Heading1"], fontName=font_name, fontSize=18, leading=24),
        "h2": ParagraphStyle("h2_vn", parent=base["Heading2"], fontName=font_name, fontSize=13, leading=18),
        "normal": ParagraphStyle("normal_vn", parent=base["BodyText"], fontName=font_name, fontSize=10.5, leading=14),
    }


def _level_distribution(students: list[dict[str, Any]]) -> dict[str, int]:
    dist = {"gioi": 0, "kha": 0, "trung_binh": 0, "yeu": 0}
    for s in students:
        score = s.get("final_score")
        if score is None:
            continue
        score = float(score)
        if score >= 85:
            dist["gioi"] += 1
        elif score >= 70:
            dist["kha"] += 1
        elif score >= 50:
            dist["trung_binh"] += 1
        else:
            dist["yeu"] += 1
    return dist


def _histogram_chart(students: list[dict[str, Any]], title: str) -> Drawing:
    bins = [0] * 5  # 0-20 ... 80-100
    for s in students:
        score = s.get("final_score")
        if score is None:
            continue
        idx = min(4, int(float(score) // 20))
        bins[idx] += 1

    drawing = Drawing(480, 220)
    chart = VerticalBarChart()
    chart.x = 40
    chart.y = 40
    chart.height = 130
    chart.width = 400
    chart.data = [bins]
    chart.strokeColor = colors.black
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = max(1, max(bins) + 1)
    chart.valueAxis.valueStep = 1
    chart.categoryAxis.categoryNames = ["0-20", "20-40", "40-60", "60-80", "80-100"]
    chart.bars[0].fillColor = colors.HexColor("#2563EB")
    drawing.add(String(40, 185, title, fontName="Helvetica-Bold", fontSize=10))
    drawing.add(chart)
    return drawing


def _pre_post_chart(students: list[dict[str, Any]], title: str) -> Drawing:
    top_students = students[:8]
    pre = [float(s.get("placement_score") or 0.0) for s in top_students]
    post = [float(s.get("final_score") or 0.0) for s in top_students]
    labels = [str(s.get("student_name") or s.get("name") or f"HS{i+1}")[:12] for i, s in enumerate(top_students)]

    drawing = Drawing(480, 240)
    chart = VerticalBarChart()
    chart.x = 40
    chart.y = 55
    chart.height = 140
    chart.width = 400
    chart.data = [pre, post]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.angle = 20
    chart.categoryAxis.labels.dy = -15
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 100
    chart.valueAxis.valueStep = 10
    chart.barSpacing = 3
    chart.groupSpacing = 8
    chart.bars[0].fillColor = colors.HexColor("#F59E0B")
    chart.bars[1].fillColor = colors.HexColor("#10B981")
    drawing.add(String(40, 208, title, fontName="Helvetica-Bold", fontSize=10))
    drawing.add(String(40, 18, "Cam: Điểm đầu vào | Xanh: Điểm cuối", fontName="Helvetica", fontSize=9))
    drawing.add(chart)
    return drawing


def _latest_pre_post_attempts(db: Session, classroom_id: int, student_id: int) -> tuple[Attempt | None, Attempt | None]:
    rows = (
        db.query(ClassroomAssessment.assessment_id, QuizSet.kind)
        .join(QuizSet, QuizSet.id == ClassroomAssessment.assessment_id)
        .filter(
            ClassroomAssessment.classroom_id == int(classroom_id),
            QuizSet.kind.in_(["diagnostic_pre", "diagnostic_post"]),
        )
        .all()
    )
    kind_by_quiz = {int(qid): str(kind or "") for qid, kind in rows}
    quiz_ids = list(kind_by_quiz.keys())
    if not quiz_ids:
        return None, None

    attempts = (
        db.query(Attempt)
        .filter(Attempt.user_id == int(student_id), Attempt.quiz_set_id.in_(quiz_ids))
        .order_by(Attempt.created_at.desc())
        .all()
    )
    pre_attempt = next((a for a in attempts if kind_by_quiz.get(int(a.quiz_set_id)) == "diagnostic_pre"), None)
    post_attempt = next((a for a in attempts if kind_by_quiz.get(int(a.quiz_set_id)) == "diagnostic_post"), None)
    return pre_attempt, post_attempt


def generate_classroom_report_pdf(db: Session, classroom_id: int) -> Path:
    classroom_id = int(classroom_id)
    report = generate_full_teacher_report(classroom_id=classroom_id, db=db)
    students = report.get("per_student") or []
    summary = report.get("summary") or {}

    all_breakdowns = []
    for student in students:
        sid = int(student.get("student_id") or 0)
        _pre, post = _latest_pre_post_attempts(db, classroom_id=classroom_id, student_id=sid)
        if post and isinstance(post.breakdown_json, list):
            all_breakdowns.append(score_breakdown(post.breakdown_json or []))

    weak_topics = analyze_topic_weak_points(all_breakdowns)
    avg_percent = float(summary.get("students_with_final") and sum(float(s.get("final_score") or 0) for s in students if s.get("final_score") is not None) / max(1, int(summary.get("students_with_final") or 0)) or 0)
    level_dist = _level_distribution(students)

    fd, output = tempfile.mkstemp(prefix=f"classroom_{classroom_id}_", suffix=".pdf")
    os.close(fd)
    out = Path(output)

    font = _register_font()
    styles = _build_styles(font)
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=28, rightMargin=28, topMargin=24, bottomMargin=24)
    story: list[Any] = [
        Paragraph(f"Báo cáo lớp học: {report.get('classroom_name') or f'Lớp {classroom_id}'}", styles["title"]),
        Paragraph(f"Thời gian xuất: {datetime.now(timezone.utc).astimezone().strftime('%d/%m/%Y %H:%M:%S')}", styles["normal"]),
        Spacer(1, 10),
        Paragraph("Tổng quan lớp", styles["h2"]),
    ]

    summary_rows = [
        ["Số học sinh", str(summary.get("total_students") or 0)],
        ["Điểm trung bình (%)", f"{avg_percent:.2f}"],
        ["Phân bố mức", ", ".join(f"{k}: {v}" for k, v in level_dist.items())],
        ["Cải thiện trung bình", f"{float(summary.get('avg_improvement') or 0):.2f}"],
    ]
    summary_table = Table(summary_rows, colWidths=[150, 350])
    summary_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.extend([summary_table, Spacer(1, 12)])

    story.extend([
        Paragraph("Phân bố điểm cuối kỳ", styles["h2"]),
        _histogram_chart(students, "Histogram điểm trung bình (%)"),
        Spacer(1, 8),
        Paragraph("So sánh đầu vào và cuối kỳ", styles["h2"]),
        _pre_post_chart(students, "Biểu đồ tiến bộ Pre/Post"),
        Spacer(1, 10),
        Paragraph("Danh sách chủ đề yếu", styles["h2"]),
    ])

    weak_rows = [["Chủ đề", "Điểm TB", "Số HS yếu", "Gợi ý"]]
    for topic in weak_topics[:10]:
        weak_rows.append([
            str(topic.get("topic") or ""),
            str(topic.get("avg_pct") or ""),
            f"{topic.get('weak_count')}/{topic.get('total')}",
            str(topic.get("suggestion") or ""),
        ])
    weak_table = Table(weak_rows, repeatRows=1, colWidths=[110, 70, 75, 245])
    weak_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
    ]))
    story.extend([weak_table, Spacer(1, 10)])

    ai_narrative = report.get("ai_class_narrative") or report.get("class_summary", {}).get("overall_assessment")
    if ai_narrative:
        story.extend([
            Paragraph("Nhận định AI", styles["h2"]),
            Paragraph(str(ai_narrative), styles["normal"]),
        ])

    doc.build(story)
    return out


def generate_student_report_pdf(db: Session, classroom_id: int, student_id: int) -> Path:
    classroom_id = int(classroom_id)
    student_id = int(student_id)
    student = db.query(User).filter(User.id == student_id).first()
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
    pre_attempt, post_attempt = _latest_pre_post_attempts(db, classroom_id=classroom_id, student_id=student_id)

    pre = float(pre_attempt.score_percent or 0) if pre_attempt else 0.0
    post = float(post_attempt.score_percent or 0) if post_attempt else 0.0
    delta = round(post - pre, 2)

    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == student_id).first()
    mastery = profile.mastery_json if profile and isinstance(profile.mastery_json, dict) else {}

    source_breakdown = score_breakdown((post_attempt or pre_attempt).breakdown_json or []) if (post_attempt or pre_attempt) else {"by_topic": {}}
    recommendations = build_recommendations(
        breakdown=source_breakdown,
        document_topics=[str(k) for k in mastery.keys()],
    )

    fd, output = tempfile.mkstemp(prefix=f"student_{student_id}_", suffix=".pdf")
    os.close(fd)
    out = Path(output)

    font = _register_font()
    styles = _build_styles(font)
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=28, rightMargin=28, topMargin=24, bottomMargin=24)
    story: list[Any] = [
        Paragraph("Báo cáo học viên", styles["title"]),
        Paragraph(f"Học viên: {getattr(student, 'full_name', None) or f'User #{student_id}'}", styles["normal"]),
        Paragraph(f"Lớp: {getattr(classroom, 'name', None) or f'Lớp {classroom_id}'}", styles["normal"]),
        Paragraph(f"Thời gian xuất: {datetime.now(timezone.utc).astimezone().strftime('%d/%m/%Y %H:%M:%S')}", styles["normal"]),
        Spacer(1, 10),
        Paragraph("Kết quả Pre/Post", styles["h2"]),
    ]

    score_table = Table([
        ["Điểm đầu vào", "Điểm cuối kỳ", "Delta"],
        [f"{pre:.2f}", f"{post:.2f}", f"{delta:+.2f}"],
    ], colWidths=[170, 170, 160])
    score_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story.extend([score_table, Spacer(1, 12), Paragraph("Bảng mastery theo chủ đề", styles["h2"])])

    mastery_rows = [["Chủ đề", "Mức độ"]]
    for topic, level in mastery.items():
        mastery_rows.append([str(topic), str(level)])
    if len(mastery_rows) == 1:
        mastery_rows.append(["(chưa có dữ liệu)", "-"])

    mastery_table = Table(mastery_rows, repeatRows=1, colWidths=[260, 240])
    mastery_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
    ]))
    story.extend([mastery_table, Spacer(1, 12), Paragraph("Khuyến nghị học tập", styles["h2"])])

    bullets = []
    for rec in recommendations[:8]:
        line = f"{rec.get('topic', 'N/A')}: {rec.get('material', '')}. {rec.get('exercise', '')}"
        bullets.append(ListItem(Paragraph(line, styles["normal"])))
    if not bullets:
        bullets.append(ListItem(Paragraph("Tiếp tục duy trì tiến độ học tập hiện tại.", styles["normal"])))
    story.append(ListFlowable(bullets, bulletType="bullet", leftPadding=18))

    doc.build(story)
    return out
