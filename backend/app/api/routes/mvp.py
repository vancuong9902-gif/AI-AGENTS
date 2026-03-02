from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.mvp import Course, Exam, Question, Result, Topic
from app.models.user import User

router = APIRouter(prefix="/mvp", tags=["mvp"])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "n/a")


def _extract_pdf_text(upload: UploadFile) -> str:
    try:
        reader = PdfReader(upload.file)
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        return re.sub(r"\s+", " ", text).strip()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid PDF: {exc}") from exc


def _generate_topics(text: str) -> list[dict[str, Any]]:
    chunks = [c.strip() for c in re.split(r"(?<=[.!?])\s+", text) if c.strip()][:40]
    topics: list[dict[str, Any]] = []
    step = max(1, len(chunks) // 8)
    for i in range(0, min(len(chunks), step * 10), step):
        idx = len(topics) + 1
        block = chunks[i : i + step]
        summary = " ".join(block)[:240] or f"Core idea {idx} from source document."
        topics.append(
            {
                "title": f"Topic {idx}",
                "summary": summary,
                "exercises": [f"Exercise {idx}.1", f"Exercise {idx}.2", f"Exercise {idx}.3"],
            }
        )
        if len(topics) >= 10:
            break
    while len(topics) < 5:
        idx = len(topics) + 1
        topics.append({"title": f"Topic {idx}", "summary": f"Summary for topic {idx}", "exercises": [f"Exercise {idx}.1", f"Exercise {idx}.2", f"Exercise {idx}.3"]})
    return topics


def _generate_questions(text: str) -> list[dict[str, Any]]:
    difficulties = ["easy"] * 4 + ["medium"] * 3 + ["hard"] * 3
    seeds = [s.strip() for s in text.split(".") if s.strip()][:10]
    questions = []
    for i, diff in enumerate(difficulties, 1):
        seed = seeds[i - 1] if i - 1 < len(seeds) else f"course concept {i}"
        questions.append(
            {
                "question": f"({diff}) Which statement best matches: {seed[:80]}?",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "answer": "Option A",
                "difficulty": diff,
            }
        )
    return questions


def _classify(score: float) -> str:
    if score < 5:
        return "Beginner"
    if score <= 7:
        return "Intermediate"
    return "Advanced"


@router.post("/courses/upload")
def upload_course(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db), teacher: User = Depends(require_roles("teacher"))):
    text = _extract_pdf_text(file)
    if not text:
        text = "Demo PDF content placeholder for MVP."
    course = Course(teacher_id=int(teacher.id), title=file.filename or "Uploaded course", source_text=text)
    db.add(course)
    db.commit()
    db.refresh(course)
    return {"request_id": _rid(request), "data": {"course_id": course.id, "title": course.title}, "error": None}


@router.post("/courses/{course_id}/generate-topics")
def generate_topics(course_id: int, request: Request, db: Session = Depends(get_db), teacher: User = Depends(require_roles("teacher"))):
    course = db.query(Course).filter(Course.id == course_id, Course.teacher_id == int(teacher.id)).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    db.query(Topic).filter(Topic.course_id == course_id).delete()
    topics = _generate_topics(course.source_text)
    for t in topics:
        db.add(Topic(course_id=course_id, title=t["title"], summary=t["summary"], exercises_json=json.dumps(t["exercises"], ensure_ascii=False)))
    db.commit()
    return {"request_id": _rid(request), "data": {"topics": topics}, "error": None}


@router.post("/courses/{course_id}/generate-entry-test")
def generate_entry_test(course_id: int, request: Request, db: Session = Depends(get_db), teacher: User = Depends(require_roles("teacher"))):
    course = db.query(Course).filter(Course.id == course_id, Course.teacher_id == int(teacher.id)).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    exam = Exam(course_id=course_id, duration_seconds=600)
    db.add(exam)
    db.flush()
    questions = _generate_questions(course.source_text)
    for q in questions:
        db.add(Question(exam_id=exam.id, question_text=q["question"], options_json=json.dumps(q["options"]), answer=q["answer"], difficulty=q["difficulty"]))
    db.commit()
    return {"request_id": _rid(request), "data": {"exam_id": exam.id, "duration_seconds": 600, "questions": questions}, "error": None}


@router.get("/student/course")
def student_course(request: Request, db: Session = Depends(get_db), student: User = Depends(require_roles("student"))):
    _ = student
    course = db.query(Course).order_by(Course.id.desc()).first()
    if not course:
        return {"request_id": _rid(request), "data": {"message": "No course available."}, "error": None}
    topics = db.query(Topic).filter(Topic.course_id == course.id).all()
    payload = [{"title": t.title, "summary": t.summary, "exercises": json.loads(t.exercises_json)} for t in topics]
    return {"request_id": _rid(request), "data": {"course_id": course.id, "topics": payload}, "error": None}


@router.get("/student/exams/latest")
def latest_exam(request: Request, db: Session = Depends(get_db), student: User = Depends(require_roles("student"))):
    _ = student
    exam = db.query(Exam).order_by(Exam.id.desc()).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Entry test not generated")
    questions = db.query(Question).filter(Question.exam_id == exam.id).all()
    return {"request_id": _rid(request), "data": {"exam_id": exam.id, "duration_seconds": exam.duration_seconds, "questions": [{"id": q.id, "question": q.question_text, "options": json.loads(q.options_json), "difficulty": q.difficulty} for q in questions]}, "error": None}


@router.post("/student/exams/{exam_id}/submit")
def submit_exam(exam_id: int, payload: dict[str, Any], request: Request, db: Session = Depends(get_db), student: User = Depends(require_roles("student"))):
    questions = db.query(Question).filter(Question.exam_id == exam_id).all()
    if not questions:
        raise HTTPException(status_code=404, detail="Exam not found")
    answers = payload.get("answers", {}) if isinstance(payload, dict) else {}
    correct = sum(1 for q in questions if answers.get(str(q.id)) == q.answer)
    score = round(correct / len(questions) * 10, 2)
    result = Result(exam_id=exam_id, student_id=int(student.id), score=score, level=_classify(score))
    db.add(result)
    db.commit()
    return {"request_id": _rid(request), "data": {"score": score, "level": result.level}, "error": None}


@router.get("/teacher/results")
def list_results(request: Request, page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db), teacher: User = Depends(require_roles("teacher"))):
    _ = teacher
    q = db.query(Result).order_by(Result.id.desc())
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    return {"request_id": _rid(request), "data": {"items": [{"result_id": r.id, "student_id": r.student_id, "score": r.score, "level": r.level} for r in rows], "pagination": {"page": page, "page_size": page_size, "total": total}}, "error": None}


@router.post("/student/tutor")
def tutor(payload: dict[str, Any], request: Request, db: Session = Depends(get_db), student: User = Depends(require_roles("student"))):
    _ = student
    question = (payload.get("question") or "").strip().lower()
    course = db.query(Course).order_by(Course.id.desc()).first()
    if not course:
        raise HTTPException(status_code=404, detail="No course available.")
    source = course.source_text.lower()
    tokens = [t for t in re.findall(r"\w+", question) if len(t) > 4]
    if not tokens or not any(t in source for t in tokens):
        answer = "This question is outside the current course scope."
    else:
        answer = f"Based on course text: {course.source_text[:220]}..."
    return {"request_id": _rid(request), "data": {"answer": answer}, "error": None}
