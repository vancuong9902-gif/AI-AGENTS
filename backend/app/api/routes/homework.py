from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.attempt import Attempt
from app.models.document_topic import DocumentTopic
from app.models.quiz_set import QuizSet
from app.schemas.homework import (
    HomeworkAnswerRequest,
    HomeworkAnswerResponse,
    HomeworkGradeRequest,
    HomeworkGradeResult,
    HomeworkSubmitRequest,
    HomeworkSubmitResponse,
)
from app.services.heuristic_grader import grade_essay_heuristic
from app.services.homework_service import generate_homework, grade_homework
from app.services.learning_plan_storage_service import grade_homework_from_plan

router = APIRouter(tags=["homework"])


@router.get("/v1/homework")
def homework_by_topic(request: Request, topicId: int, userId: int, db: Session = Depends(get_db)):
    topic = db.query(DocumentTopic).filter(DocumentTopic.id == int(topicId)).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    generated = generate_homework(topic, n_questions=8)
    items = []
    for idx, item in enumerate(generated):
        options = item.get("options") if isinstance(item.get("options"), list) else []
        answer = item.get("answer")
        correct_index = -1
        if options and answer is not None:
            answer_lower = str(answer).strip().lower()
            for i, opt in enumerate(options):
                if str(opt).strip().lower() == answer_lower:
                    correct_index = i
                    break
        items.append(
            {
                "id": idx + 1,
                "questionId": idx + 1,
                "type": item.get("type") or ("mcq" if options else "essay"),
                "stem": item.get("question") or "",
                "options": options,
                "correct_answer": str(answer) if answer is not None else "",
                "correct_index": correct_index,
                "topic_id": int(topic.id),
                "topic_name": topic.display_title or topic.title,
                "user_id": int(userId),
            }
        )
    return {"request_id": request.state.request_id, "data": {"topic": topic.display_title or topic.title, "items": items}, "error": None}


@router.post("/v1/homework/generate")
def homework_generate(request: Request, topicId: int, userId: int, db: Session = Depends(get_db)):
    _ = userId
    topic = db.query(DocumentTopic).filter(DocumentTopic.id == int(topicId)).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    items = generate_homework(topic, n_questions=8)
    return {"request_id": request.state.request_id, "data": {"topic_id": int(topic.id), "count": len(items)}, "error": None}


@router.post("/homework/grade")
def homework_grade(request: Request, payload: HomeworkGradeRequest, db: Session = Depends(get_db)):
    result = grade_homework(
        db,
        user_id=int(payload.user_id),
        stem=payload.stem,
        answer_text=payload.answer_text,
        max_points=int(payload.max_points or 10),
        rubric=payload.rubric,
        sources=payload.sources,
    )

    out = HomeworkGradeResult(**result).model_dump()
    return {"request_id": request.state.request_id, "data": out, "error": None}


@router.post("/homework/{hw_id}/submit")
def homework_submit(
    request: Request,
    hw_id: int,
    payload: HomeworkSubmitRequest,
    db: Session = Depends(get_db),
):
    try:
        data = grade_homework_from_plan(
            db,
            plan_id=int(hw_id),
            user_id=int(payload.user_id),
            day_index=int(payload.day_index),
            answer_text=str(payload.answer_text or ""),
            mcq_answers={str(payload.question_id): int(payload.chosen_index)},
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    feedback = None
    for item in (data.get("mcq_breakdown") or []):
        if str(item.get("question_id")) == str(payload.question_id):
            feedback = item.get("feedback")
            break
    if not feedback:
        feedback = data.get("feedback") or {}

    out = HomeworkSubmitResponse(question_id=str(payload.question_id), feedback=feedback).model_dump(exclude_none=True)
    return {"request_id": request.state.request_id, "data": out, "error": None}


@router.post("/v1/homework/{homework_id}/answer")
def homework_answer(
    request: Request,
    homework_id: int,
    payload: HomeworkAnswerRequest,
    db: Session = Depends(get_db),
):
    topic = db.query(DocumentTopic).filter(DocumentTopic.id == int(homework_id)).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Homework topic not found")

    exercises = generate_homework(topic, n_questions=8)
    q_idx = int(payload.question_id) - 1
    if q_idx < 0 or q_idx >= len(exercises):
        raise HTTPException(status_code=404, detail="Question not found")
    question = exercises[q_idx]
    options = question.get("options") if isinstance(question.get("options"), list) else []
    correct_answer = str(question.get("answer") or "").strip()
    explanation = str(question.get("explanation") or "")
    answer_text = str(payload.answer).strip()

    if options:
        is_correct = answer_text.lower() == correct_answer.lower()
        max_points = 1
        scored = max_points if is_correct else 0
        if not explanation:
            explanation = "Đối chiếu với đáp án đúng và thử phân tích lại từng lựa chọn."
    else:
        graded = grade_essay_heuristic(
            stem=str(question.get("question") or ""),
            answer_text=answer_text,
            rubric=[],
            max_points=10,
            evidence_chunks=[],
        )
        scored = int(graded.get("score_points", 0) or 0)
        is_correct = scored >= 6
        explanation = str(graded.get("comment") or explanation or "")
        correct_answer = str(question.get("answer") or "Tham khảo phần giải thích.")

    if payload.used_hint:
        scored = int(round(scored * 0.8))

    req_user_id = int(request.headers.get("X-User-Id") or 1)
    quiz_set = (
        db.query(QuizSet)
        .filter(QuizSet.user_id == req_user_id, QuizSet.kind.in_(["homework", "quiz"]), QuizSet.topic == (topic.display_title or topic.title))
        .order_by(QuizSet.id.desc())
        .first()
    )
    if quiz_set:
        attempt = Attempt(
            user_id=req_user_id,
            quiz_set_id=int(quiz_set.id),
            score_percent=max(0, min(100, int(scored * 10 if not options else scored * 100))),
            answers_json=[{"question_id": int(payload.question_id), "answer": answer_text, "used_hint": bool(payload.used_hint)}],
            breakdown_json=[{"is_correct": bool(is_correct), "score_points": int(scored), "correct_answer": correct_answer}],
            duration_sec=0,
        )
        db.add(attempt)
        db.commit()

    out = HomeworkAnswerResponse(
        is_correct=bool(is_correct),
        score_points=int(scored),
        explanation=explanation,
        correct_answer=correct_answer,
    ).model_dump()
    return {"request_id": request.state.request_id, "data": out, "error": None}
