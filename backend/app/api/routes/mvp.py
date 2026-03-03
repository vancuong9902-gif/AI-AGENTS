from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.core.config import settings
from app.models.classroom import Classroom, ClassroomMember
from app.models.mvp import Course, Exam, Question, Result, Topic
from app.models.user import User
from app.services.llm_service import chat_json, llm_available

router = APIRouter(prefix="/mvp", tags=["mvp"])


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "n/a")




def _has_student_material(db: Session, student_id: int) -> bool:
    memberships = db.query(ClassroomMember.classroom_id).filter(ClassroomMember.user_id == int(student_id)).all()
    classroom_ids = [int(row[0]) for row in memberships if row and row[0] is not None]
    if not classroom_ids:
        return False

    # New flow: classroom must be linked to a course and that course must have topics (published).
    if hasattr(Classroom, "course_id"):
        classrooms = db.query(Classroom).filter(Classroom.id.in_(classroom_ids)).all()
        for classroom in classrooms:
            class_course_id = getattr(classroom, "course_id", None)
            if class_course_id is None:
                continue
            topic_count = db.query(Topic).filter(Topic.course_id == int(class_course_id)).count()
            if topic_count > 0:
                return True
        return False

    # Legacy fallback for schema without classrooms.course_id.
    course = db.query(Course).order_by(Course.id.desc()).first()
    if not course:
        return False
    return db.query(Topic).filter(Topic.course_id == int(course.id)).count() > 0


def require_student_material(
    db: Session = Depends(get_db),
    student: User = Depends(require_roles("student")),
) -> User:
    if not _has_student_material(db, int(student.id)):
        raise HTTPException(status_code=404, detail="Lớp học chưa có tài liệu")
    return student


def _extract_pdf_text(upload: UploadFile) -> str:
    try:
        reader = PdfReader(upload.file)
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        return re.sub(r"\s+", " ", text).strip()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid PDF: {exc}") from exc


def _generate_topics(text: str) -> list[dict[str, Any]]:
    if llm_available():
        try:
            result = chat_json(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Bạn là chuyên gia giáo dục. Phân tích tài liệu và tạo danh sách chủ đề học tập. "
                            "Trả về JSON với key 'topics' là mảng, mỗi phần tử gồm: "
                            "'title' (tên chủ đề ngắn gọn), "
                            "'summary' (tóm tắt 2-3 câu), "
                            "'exercises' (mảng 3 bài tập thực hành cụ thể từ nội dung). "
                            "Tạo 5-8 chủ đề bám sát tài liệu. CHỈ trả về JSON thuần, không có text thừa."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Tài liệu:\n{text[:6000]}\n\nTạo danh sách topics học tập.",
                    },
                ],
                max_tokens=2000,
                temperature=0.4,
            )
            topics = result.get("topics", [])
            if isinstance(topics, list) and len(topics) >= 3:
                return [
                    {
                        "title": str(t.get("title", f"Topic {i+1}")),
                        "summary": str(t.get("summary", "")),
                        "exercises": list(t.get("exercises", [])) if isinstance(t.get("exercises"), list) else [],
                    }
                    for i, t in enumerate(topics[:10])
                ]
        except Exception:
            pass

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
    if llm_available():
        try:
            result = chat_json(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Bạn là giáo viên tạo bài kiểm tra trắc nghiệm. "
                            "Trả về JSON với key 'questions' là mảng 10 câu hỏi, mỗi câu gồm: "
                            "'question' (câu hỏi rõ ràng bằng tiếng Việt), "
                            "'options' (mảng đúng 4 string: ['A. ...', 'B. ...', 'C. ...', 'D. ...']), "
                            "'answer' (phải khớp chính xác 1 trong 4 options), "
                            "'difficulty' (easy/medium/hard, tỉ lệ: 4 easy, 3 medium, 3 hard). "
                            "Câu hỏi phải bám sát nội dung tài liệu. CHỈ trả về JSON thuần."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Tài liệu:\n{text[:6000]}\n\nTạo 10 câu hỏi trắc nghiệm.",
                    },
                ],
                max_tokens=3000,
                temperature=0.3,
            )
            questions = result.get("questions", [])
            if isinstance(questions, list) and len(questions) >= 5:
                valid = []
                for q in questions[:10]:
                    opts = q.get("options", [])
                    ans = q.get("answer", "")
                    if isinstance(opts, list) and len(opts) == 4 and ans in opts:
                        valid.append(
                            {
                                "question": str(q.get("question", "")),
                                "options": [str(o) for o in opts],
                                "answer": str(ans),
                                "difficulty": str(q.get("difficulty", "medium")),
                            }
                        )
                if len(valid) >= 5:
                    return valid
        except Exception:
            pass

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
    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()
    is_pdf = filename.endswith(".pdf") or content_type == "application/pdf"
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    max_bytes = int(settings.MAX_UPLOAD_MB) * 1024 * 1024
    content = file.file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {settings.MAX_UPLOAD_MB}MB.",
        )
    import io

    file.file = io.BytesIO(content)

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
def student_course(request: Request, db: Session = Depends(get_db), student: User = Depends(require_student_material)):
    _ = student
    course = db.query(Course).order_by(Course.id.desc()).first()
    if not course:
        return {"request_id": _rid(request), "data": {"message": "No course available."}, "error": None}
    topics = db.query(Topic).filter(Topic.course_id == course.id).all()
    payload = [{"title": t.title, "summary": t.summary, "exercises": json.loads(t.exercises_json)} for t in topics]
    return {"request_id": _rid(request), "data": {"course_id": course.id, "topics": payload}, "error": None}


@router.get("/student/exams/latest")
def latest_exam(request: Request, db: Session = Depends(get_db), student: User = Depends(require_student_material)):
    _ = student
    exam = db.query(Exam).order_by(Exam.id.desc()).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Entry test not generated")
    questions = db.query(Question).filter(Question.exam_id == exam.id).all()
    return {"request_id": _rid(request), "data": {"exam_id": exam.id, "duration_seconds": exam.duration_seconds, "questions": [{"id": q.id, "question": q.question_text, "options": json.loads(q.options_json), "difficulty": q.difficulty} for q in questions]}, "error": None}


@router.post("/student/exams/{exam_id}/submit")
def submit_exam(exam_id: int, payload: dict[str, Any], request: Request, db: Session = Depends(get_db), student: User = Depends(require_student_material)):
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
def tutor(payload: dict[str, Any], request: Request, db: Session = Depends(get_db), student: User = Depends(require_student_material)):
    _ = student
    question = (payload.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required.")

    course = db.query(Course).order_by(Course.id.desc()).first()
    if not course:
        raise HTTPException(status_code=404, detail="No course available.")

    if llm_available():
        try:
            result = chat_json(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Bạn là AI Tutor hỗ trợ học sinh học tập. "
                            "Chỉ trả lời dựa trên tài liệu được cung cấp, không dùng kiến thức ngoài. "
                            "Trả về JSON với key 'answer' (string, giải thích rõ ràng bằng tiếng Việt). "
                            "Nếu câu hỏi ngoài phạm vi tài liệu, trả 'answer': "
                            "'Câu hỏi này nằm ngoài nội dung tài liệu hiện tại. "
                            "Vui lòng hỏi về nội dung trong tài liệu.'"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Tài liệu tham khảo:\n{course.source_text[:4000]}\n\nCâu hỏi: {question}",
                    },
                ],
                max_tokens=800,
                temperature=0.5,
            )
            answer = str(result.get("answer") or "Tôi không thể trả lời câu hỏi này lúc này.")
            return {"request_id": _rid(request), "data": {"answer": answer}, "error": None}
        except Exception:
            pass

    source = course.source_text.lower()
    tokens = [t for t in re.findall(r"\w+", question.lower()) if len(t) > 4]
    if not tokens or not any(t in source for t in tokens):
        answer = "Câu hỏi này nằm ngoài phạm vi nội dung tài liệu hiện tại."
    else:
        answer = f"Dựa trên tài liệu: {course.source_text[:300]}..."
    return {"request_id": _rid(request), "data": {"answer": answer}, "error": None}


@router.get("/student/status")
def student_status(
    request: Request,
    db: Session = Depends(get_db),
    student: User = Depends(require_roles("student")),
):
    _ = student
    course = db.query(Course).order_by(Course.id.desc()).first()
    has_course = course is not None
    has_topics = False
    has_exam = False
    if course:
        has_topics = db.query(Topic).filter(Topic.course_id == course.id).count() > 0
        has_exam = db.query(Exam).filter(Exam.course_id == course.id).count() > 0
    return {
        "request_id": _rid(request),
        "data": {
            "ready": has_course and has_topics and has_exam,
            "has_course": has_course,
            "has_topics": has_topics,
            "has_exam": has_exam,
            "has_content": _has_student_material(db, int(student.id)),
        },
        "error": None,
    }
