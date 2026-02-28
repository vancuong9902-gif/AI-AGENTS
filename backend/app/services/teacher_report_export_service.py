from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from app.models.attempt import Attempt
from app.models.classroom import ClassroomMember
from app.models.classroom_assessment import ClassroomAssessment
from app.models.quiz_set import QuizSet
from app.services.lms_service import (
    generate_student_evaluation_report,
    resolve_student_name,
    score_breakdown,
    get_student_homework_results,
)


def _wrap(text: str, width: int = 90) -> list[str]:
    words = (text or "").split()
    out: list[str] = []
    line: list[str] = []
    for w in words:
        test = " ".join(line + [w])
        if len(test) > width and line:
            out.append(" ".join(line))
            line = [w]
        else:
            line.append(w)
    if line:
        out.append(" ".join(line))
    return out or [""]


def build_classroom_report_pdf(classroom_id: int, db: Session) -> str:
    assessment_ids = [
        int(r[0])
        for r in db.query(ClassroomAssessment.assessment_id)
        .filter(ClassroomAssessment.classroom_id == int(classroom_id))
        .all()
    ]
    members = [
        int(r[0])
        for r in db.query(ClassroomMember.user_id)
        .filter(ClassroomMember.classroom_id == int(classroom_id))
        .all()
    ]
    attempts = db.query(Attempt).filter(Attempt.quiz_set_id.in_(assessment_ids)).all() if assessment_ids else []
    quiz_kind_map = {
        int(qid): str(kind or "")
        for qid, kind in db.query(QuizSet.id, QuizSet.kind).filter(QuizSet.id.in_(assessment_ids)).all()
    } if assessment_ids else {}

    per_student: dict[int, dict[str, Any]] = {uid: {"pre": {}, "post": {}} for uid in members}
    for at in attempts:
        uid = int(at.user_id)
        if uid not in per_student:
            per_student[uid] = {"pre": {}, "post": {}}
        kind = quiz_kind_map.get(int(at.quiz_set_id), "")
        br = score_breakdown(at.breakdown_json or [])
        if kind == "diagnostic_pre":
            per_student[uid]["pre"] = br
        elif kind == "diagnostic_post":
            per_student[uid]["post"] = br

    fd, out_path = tempfile.mkstemp(prefix=f"classroom_report_{classroom_id}_", suffix=".pdf")
    Path(out_path).unlink(missing_ok=True)

    c = canvas.Canvas(out_path, pagesize=A4)
    w, h = A4
    y = h - 40

    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, f"Bao cao lop {classroom_id} - Danh gia hoc sinh")
    y -= 30

    for uid in sorted(per_student):
        data = per_student[uid]
        eval_report = generate_student_evaluation_report(
            student_id=uid,
            pre_attempt=data.get("pre") or {},
            post_attempt=data.get("post") or {},
            homework_results=get_student_homework_results(uid, db),
            db=db,
        )
        name = resolve_student_name(uid, db)

        lines = [
            f"- HS {uid} | {name}",
            f"  Diem dau vao: {float((data.get('pre') or {}).get('overall', {}).get('percent') or 0.0):.1f}%",
            f"  Diem cuoi ky: {float((data.get('post') or {}).get('overall', {}).get('percent') or 0.0):.1f}%",
            f"  Xep loai: {eval_report.get('overall_grade', 'N/A')}",
            f"  Diem manh: {', '.join(eval_report.get('strengths') or []) or 'N/A'}",
            f"  Can cai thien: {', '.join(eval_report.get('weaknesses') or []) or 'N/A'}",
            f"  Nhan xet: {eval_report.get('ai_comment', '')}",
        ]
        for raw in lines:
            for line in _wrap(raw, width=95):
                if y < 50:
                    c.showPage()
                    c.setFont("Helvetica", 10)
                    y = h - 40
                c.setFont("Helvetica", 10)
                c.drawString(40, y, line)
                y -= 14
        y -= 8

    c.save()
    return out_path
