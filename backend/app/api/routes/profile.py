from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.learner_profile import LearnerProfile
from app.models.diagnostic_attempt import DiagnosticAttempt
from app.models.attempt import Attempt
from app.models.quiz_set import QuizSet
from app.services.user_service import ensure_user_exists
from app.services.rag_service import retrieve_and_log, auto_document_ids_for_query
from app.core.config import settings
from app.services.llm_service import llm_available, chat_json, pack_chunks
from app.services.lms_service import classify_student_level
from app.schemas.profile import (
    DiagnosticQuestionOut,
    DiagnosticRequest,
    DiagnosticResultData,
    FinalResultData,
    LearnerProfileData,
    NextRecommendationData,
    LearningMaterial,
    LearningModule,
    LearningPathData,
)

router = APIRouter(tags=["profile"])


# ===== Learning Path helpers (topic -> query -> relevant chunks -> study material) =====

_GENERIC_TOPICS = {
    "tài liệu",
    "python cơ bản",
    "python co ban",
    "python basics",
    "cơ bản",
    "co ban",
}

# Canonical topic -> keyword hints (Vietnamese + common tokens)
_TOPIC_HINTS = {
    "biến & kiểu dữ liệu": ["biến", "kiểu dữ liệu", "int", "float", "str", "boolean", "bool", "none"],
    "list/tuple/dict": ["list", "tuple", "dict", "dictionary", "set", "mảng", "phần tử", "index", "slice"],
    "vòng lặp": ["vòng lặp", "for", "while", "break", "continue", "range"],
    "hàm": ["hàm", "function", "def", "tham số", "parameter", "return", "lambda"],
    "oop cơ bản": ["class", "object", "self", "__init__", "method", "thuộc tính", "kế thừa", "inherit"],
    "numpy cơ bản": ["numpy", "ndarray", "array", "shape", "dtype", "broadcast", "vector", "matrix"],
    "sql": ["sql", "select", "where", "join", "group by", "insert", "update"],
    "rag": ["rag", "retrieval", "embedding", "vector", "faiss", "chunk", "context"],
}


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _is_generic_topic(topic: str) -> bool:
    t = _norm(topic)
    if not t:
        return True
    if t in _GENERIC_TOPICS:
        return True
    # overly broad topics often include doc titles like "python cơ bản"
    if "python" in t and ("cơ bản" in t or "co ban" in t):
        return True
    return False


def _expand_topic(topic: str) -> list[str]:
    """If topic is too generic, expand into a small curriculum-friendly set."""
    t = _norm(topic)
    if _is_generic_topic(t):
        return [
            "biến & kiểu dữ liệu",
            "list/tuple/dict",
            "vòng lặp",
            "hàm",
            "oop cơ bản",
        ]
    return [topic]


def _topic_keywords(topic: str) -> list[str]:
    t = _norm(topic)
    if not t:
        return []
    # exact match in hints
    if t in _TOPIC_HINTS:
        return _TOPIC_HINTS[t]
    # partial match: if any canonical key is contained
    for k, kws in _TOPIC_HINTS.items():
        if k in t or t in k:
            return kws
    # fallback: use tokens from topic itself
    toks = [x for x in t.replace("/", " ").replace("&", " ").split() if x]
    return toks[:8]


def _build_rag_query(topic: str, level: str | None = None) -> str:
    t = (topic or "").strip()
    # make query specific to avoid matching the whole document title everywhere
    if _is_generic_topic(t):
        return "python khái niệm cơ bản: biến kiểu dữ liệu list tuple dict vòng lặp hàm class"
    if (level or "").lower() == "advanced":
        return f"{t} python tình huống ví dụ lỗi thường gặp"
    if (level or "").lower() == "intermediate":
        return f"{t} python giải thích so sánh ví dụ"
    return f"{t} python khái niệm ví dụ"


def _relevance_score(topic: str, chunk_text: str) -> int:
    text = _norm(chunk_text)
    if not text:
        return 0
    kws = _topic_keywords(topic)
    if not kws:
        return 0
    score = 0
    for kw in kws:
        kw_n = _norm(kw)
        if not kw_n:
            continue
        if kw_n in text:
            score += 1
    return score


def _select_relevant_chunks(topic: str, chunks: list[dict], limit: int) -> list[dict]:
    # score chunks by (topic keyword hits, original score)
    scored = []
    for c in chunks or []:
        txt = c.get("text") or ""
        rs = _relevance_score(topic, txt)
        # keep if relevant OR topic is generic
        if rs <= 0 and (not _is_generic_topic(topic)):
            continue
        try:
            base = float(c.get("score", 0.0) or 0.0)
        except Exception:
            base = 0.0
        scored.append((rs, base, c))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    out = [c for _, _, c in scored]
    # dedup by chunk_id
    seen = set()
    uniq = []
    for c in out:
        cid = c.get("chunk_id")
        if cid in seen:
            continue
        seen.add(cid)
        uniq.append(c)
        if len(uniq) >= max(1, int(limit)):
            break
    return uniq


def _offline_lesson(topic: str, level: str, mastery: float, chunks: list[dict]) -> str:
    """Generate a simple study note without LLM (still better than raw chunks)."""
    t = (topic or "tài liệu").strip()
    lvl = (level or "beginner").lower()
    pct = int(round((mastery or 0.0) * 100))

    picked = _select_relevant_chunks(t, chunks or [], limit=2)
    text = " ".join([str(c.get("text") or "").strip() for c in picked if (c.get("text") or "").strip()])
    text = " ".join(text.split())

    # pick a few sentences that likely contain useful info
    sentences = []
    if text:
        # naive split
        for part in text.replace("\n", ". ").split("."):
            s = " ".join(part.split())
            if len(s) < 30:
                continue
            sentences.append(s)
            if len(sentences) >= 4:
                break

    bullets = "\n".join([f"- {s}." for s in sentences]) if sentences else "- Ôn lại khái niệm chính và làm 1–2 ví dụ nhỏ."

    focus = {
        "beginner": "Hiểu khái niệm + làm được ví dụ đơn giản.",
        "intermediate": "Giải thích được + so sánh/đối chiếu + biết lỗi thường gặp.",
        "advanced": "Vận dụng vào tình huống + tối ưu/thiết kế hợp lý.",
    }.get(lvl, "Hiểu khái niệm + làm ví dụ.")

    return (
        f"# Tài liệu học tập: {t}\n"
        f"**Mức gợi ý:** {lvl} • **Mastery hiện tại:** {pct}%\n\n"
        f"## Mục tiêu\n{focus}\n\n"
        f"## Tóm tắt nhanh\n{bullets}\n\n"
        f"## Tự kiểm tra\n"
        f"1) {t} dùng khi nào?\n"
        f"2) Nêu 1 ví dụ ngắn về {t}.\n"
        f"3) Lỗi thường gặp liên quan đến {t} là gì?\n"
    )


# 18 câu (tăng dần độ khó). Demo-friendly: AI/Dev fundamentals.
_DIAGNOSTIC_BANK: List[Dict] = [
    {
        "id": 1,
        "topic": "Python cơ bản",
        "q": "Trong Python, kiểu dữ liệu nào là bất biến (immutable)?",
        "options": ["list", "dict", "set", "tuple"],
        "correct": 3,
    },
    {
        "id": 2,
        "topic": "Python cơ bản",
        "q": "Lệnh nào tạo môi trường ảo (venv) chuẩn trong Python?",
        "options": ["python -m venv .venv", "pip install venv", "venv create", "python venv"],
        "correct": 0,
    },
    {
        "id": 3,
        "topic": "Web/API (HTTP + FastAPI + CORS)",
        "q": "Trong HTTP, method nào thường dùng để 'tạo mới' (create) tài nguyên?",
        "options": ["GET", "POST", "PUT", "DELETE"],
        "correct": 1,
    },
    {
        "id": 4,
        "topic": "Database (SQL + Index)",
        "q": "Trong SQL, câu lệnh nào dùng để lấy dữ liệu?",
        "options": ["INSERT", "UPDATE", "SELECT", "DROP"],
        "correct": 2,
    },
    {
        "id": 5,
        "topic": "Web/API (HTTP + FastAPI + CORS)",
        "q": "Trong FastAPI, cách khai báo endpoint POST đúng là?",
        "options": ["@app.post('/path')", "app.post('/path')", "@post('/path')", "fastapi.post('/path')"],
        "correct": 0,
    },
    {
        "id": 6,
        "topic": "DevOps/Config (.env + Docker Compose)",
        "q": "Ý nghĩa của file .env trong project là gì?",
        "options": [
            "Lưu cấu hình/biến môi trường (API key, DB URL,...)",
            "Chứa code Python chính",
            "Chứa database schema",
            "Chỉ dùng cho frontend",
        ],
        "correct": 0,
    },
    {
        "id": 7,
        "topic": "DevOps/Config (.env + Docker Compose)",
        "q": "Docker Compose thường dùng để làm gì?",
        "options": [
            "Chạy nhiều service (db/backend/...) cùng lúc bằng 1 file cấu hình",
            "Thay thế hoàn toàn Dockerfile",
            "Tự động viết code backend",
            "Chỉ để build frontend",
        ],
        "correct": 0,
    },
    {
        "id": 8,
        "topic": "RAG & Vector DB",
        "q": "Trong RAG, bước 'Retrieval' là gì?",
        "options": [
            "Truy xuất đoạn văn liên quan từ tài liệu",
            "Fine-tune model",
            "Dịch tài liệu",
            "Nén ảnh",
        ],
        "correct": 0,
    },
    {
        "id": 9,
        "topic": "RAG & Vector DB",
        "q": "Embedding là gì?",
        "options": [
            "Biểu diễn văn bản thành vector số",
            "Mã hóa mật khẩu",
            "Nén file ZIP",
            "Tăng độ phân giải ảnh",
        ],
        "correct": 0,
    },
    {
        "id": 10,
        "topic": "RAG & Vector DB",
        "q": "FAISS/Chroma thường được dùng cho mục đích nào trong RAG?",
        "options": [
            "Lưu và tìm kiếm vector theo độ tương đồng",
            "Làm ORM cho SQL",
            "Tạo UI",
            "Thay thế FastAPI",
        ],
        "correct": 0,
    },
    {
        "id": 11,
        "topic": "RAG & Vector DB",
        "q": "Tại sao cần chunking tài liệu trước khi tạo embedding?",
        "options": [
            "Để phù hợp giới hạn token và tăng độ chính xác truy xuất",
            "Để đổi định dạng file",
            "Để giảm dung lượng ảnh",
            "Không cần chunking",
        ],
        "correct": 0,
    },
    {
        "id": 12,
        "topic": "Database (SQL + Index)",
        "q": "Trong DB, index (chỉ mục) thường giúp gì?",
        "options": [
            "Tăng tốc truy vấn (SELECT)",
            "Tăng kích thước file log",
            "Làm đẹp UI",
            "Tăng độ bảo mật API key",
        ],
        "correct": 0,
    },
    {
        "id": 13,
        "topic": "Web/API (HTTP + FastAPI + CORS)",
        "q": "Để tránh CORS khi frontend gọi backend khác port, cần cấu hình gì?",
        "options": ["CORSMiddleware", "JWT", "Alembic", "Redis"],
        "correct": 0,
    },
    {
        "id": 14,
        "topic": "RAG & Vector DB",
        "q": "Trong RAG, 'sources' (nguồn) trả về để làm gì?",
        "options": [
            "Giải thích câu trả lời dựa trên đoạn nào của tài liệu",
            "Tăng tốc build Docker",
            "Ẩn API key",
            "Thay thế unit test",
        ],
        "correct": 0,
    },
    {
        "id": 15,
        "topic": "Learning analytics & Profiling",
        "q": "Khi user submit quiz, server nên lưu gì tối thiểu để theo dõi học tập?",
        "options": [
            "User_id, quiz_id, answers, score, thời gian làm",
            "Chỉ lưu score",
            "Chỉ lưu câu hỏi",
            "Không cần lưu",
        ],
        "correct": 0,
    },
    {
        "id": 16,
        "topic": "Learning analytics & Profiling",
        "q": "Một rule đơn giản để cập nhật mastery theo topic là?",
        "options": [
            "Đúng +α, sai -β (clamp 0..1)",
            "Đúng -α, sai +β",
            "Luôn đặt mastery=1",
            "Không cập nhật mastery",
        ],
        "correct": 0,
    },
    {
        "id": 17,
        "topic": "Learning analytics & Profiling",
        "q": "Nếu score diagnostic là 70%, theo rule (<40 Beginner, 40-70 Intermediate, >70 Advanced) thì level là?",
        "options": ["beginner", "intermediate", "advanced", "không xác định"],
        "correct": 1,
    },
    {
        "id": 18,
        "topic": "Web/API (HTTP + FastAPI + CORS)",
        "q": "Điều nào đúng về 'idempotent' trong HTTP?",
        "options": [
            "Gọi nhiều lần vẫn ra cùng kết quả trạng thái (ví dụ PUT)",
            "Chỉ áp dụng cho POST",
            "Là thuật ngữ về embedding",
            "Chỉ có trong WebSocket",
        ],
        "correct": 0,
    },
]


def _mastery_from_diagnostic_answers(
    *, answer_map: dict[int, int], threshold: float = 0.6
) -> tuple[dict[str, float], list[str]]:
    """Compute mastery_by_topic + weak_topics for the simple diagnostic bank."""
    counts: dict[str, list[int]] = {}
    for q in _DIAGNOSTIC_BANK:
        qid = int(q.get("id"))
        topic = (q.get("topic") or "tổng quan").strip()
        chosen = int(answer_map.get(qid, -1))
        is_correct = chosen == int(q.get("correct"))
        if topic not in counts:
            counts[topic] = [0, 0]
        counts[topic][1] += 1
        if is_correct:
            counts[topic][0] += 1

    mastery_by_topic = {
        t: (float(earned) / float(total) if total else 0.0)
        for t, (earned, total) in counts.items()
    }
    weak = [t for t, v in mastery_by_topic.items() if float(v) < float(threshold)]
    weak.sort(key=lambda t: mastery_by_topic.get(t, 0.0))
    return mastery_by_topic, weak


def _level_from_score(score_percent: int) -> str:
    if score_percent < 40:
        return "beginner"
    if score_percent <= 70:
        return "intermediate"
    return "advanced"


@router.get("/profile/diagnostic/questions")
def diagnostic_questions(request: Request):
    questions = [
        DiagnosticQuestionOut(
            question_id=q["id"],
            question=q["q"],
            options=q["options"],
            topic=q.get("topic"),
        ).model_dump()
        for q in _DIAGNOSTIC_BANK
    ]
    return {"request_id": request.state.request_id, "data": {"questions": questions}, "error": None}


@router.post("/profile/diagnostic")
def diagnostic_submit(request: Request, payload: DiagnosticRequest, db: Session = Depends(get_db)):
    ensure_user_exists(db, int(payload.user_id), role="student")

    answer_map = {a.question_id: a.answer for a in payload.answers}

    correct_count = 0
    for q in _DIAGNOSTIC_BANK:
        chosen = int(answer_map.get(q["id"], -1))
        if chosen == int(q["correct"]):
            correct_count += 1

    total = len(_DIAGNOSTIC_BANK)
    score_percent = int(round((correct_count / total) * 100)) if total else 0
    level = _level_from_score(score_percent)

    # Mastery theo nhóm topic (để dùng cho learning path)
    mastery_by_topic, weak_topics = _mastery_from_diagnostic_answers(answer_map=answer_map, threshold=0.6)

    # Upsert learner_profile
    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == payload.user_id).first()
    if not profile:
        profile = LearnerProfile(user_id=payload.user_id, level=level, mastery_json={})
        db.add(profile)

    # Merge mastery to profile
    profile.level = level
    merged = dict(profile.mastery_json or {})
    for t, v in mastery_by_topic.items():
        merged[t] = float(v)
    merged["overall"] = float(score_percent) / 100.0
    profile.mastery_json = merged

    # Lưu attempt diagnostic (đầu vào) để so sánh về sau
    attempt = DiagnosticAttempt(
        user_id=payload.user_id,
        stage="pre",
        score_percent=score_percent,
        correct_count=correct_count,
        total=total,
        level=level,
        answers_json=[{"question_id": a.question_id, "answer": a.answer} for a in payload.answers],
        mastery_json={
            "by_topic": mastery_by_topic,
            "weak_topics": weak_topics,
            "total_percent": score_percent,
        },
    )
    db.add(attempt)

    db.commit()
    db.refresh(attempt)

    # Auto-generate & assign a learning plan right after the placement test (pre).
    # This makes the flow "test xong -> có bài tập luôn".
    plan_id: int | None = None
    try:
        from app.models.learning_plan import LearningPlan
        from app.services.learning_plan_service import build_teacher_learning_plan
        from app.services.learning_plan_storage_service import save_teacher_plan
        from app.core.config import settings as _settings

        # Idempotency: if attempt already has plan_id and it exists, keep.
        mj0 = attempt.mastery_json or {}
        if isinstance(mj0, dict) and mj0.get("plan_id") is not None:
            try:
                pid0 = int(mj0.get("plan_id"))
                if db.query(LearningPlan.id).filter(LearningPlan.id == pid0).first():
                    plan_id = pid0
            except Exception:
                plan_id = None

        if plan_id is None:
            assigned_topic = None
            try:
                # Prefer the weakest topic for the first plan.
                assigned_topic = (weak_topics or [None])[0]
                if not assigned_topic and mastery_by_topic:
                    assigned_topic = next(iter(mastery_by_topic.keys()))
            except Exception:
                assigned_topic = None

            days_total = int(getattr(_settings, "LEARNING_PLAN_DAYS", 7) or 7)
            minutes_per_day = int(getattr(_settings, "LEARNING_PLAN_MINUTES_PER_DAY", 35) or 35)

            teacher_plan = build_teacher_learning_plan(
                db,
                user_id=int(payload.user_id),
                teacher_id=int(getattr(_settings, "DEFAULT_TEACHER_ID", 1) or 1),
                level=str(level or "beginner"),
                assigned_topic=assigned_topic,
                modules=[],
                days=days_total,
                minutes_per_day=minutes_per_day,
            )

            plan_row = save_teacher_plan(
                db,
                user_id=int(payload.user_id),
                teacher_id=int(getattr(_settings, "DEFAULT_TEACHER_ID", 1) or 1),
                classroom_id=None,
                assigned_topic=assigned_topic,
                level=str(level or "beginner"),
                days_total=int(teacher_plan.days_total or days_total),
                minutes_per_day=int(teacher_plan.minutes_per_day or minutes_per_day),
                teacher_plan=teacher_plan.model_dump(),
            )
            plan_id = int(plan_row.id)

            mj1 = dict(mj0) if isinstance(mj0, dict) else {}
            mj1["plan_id"] = int(plan_id)
            attempt.mastery_json = mj1
            db.commit()
    except Exception:
        plan_id = None

    out = DiagnosticResultData(
        attempt_id=attempt.id,
        stage="pre",
        user_id=payload.user_id,
        score_percent=score_percent,
        correct_count=correct_count,
        total=total,
        level=level,
    ).model_dump()

    if plan_id is not None:
        out["plan_id"] = int(plan_id)

    return {"request_id": request.state.request_id, "data": out, "error": None}


@router.post("/profile/final")
def final_submit(request: Request, payload: DiagnosticRequest, db: Session = Depends(get_db)):
    """
    Bài test cuối kỳ (post-test): dùng cùng bộ câu hỏi với diagnostic để đo tiến bộ.
    - Không ghi đè level mặc định (để giữ phân loại đầu vào).
    - Lưu attempt stage="post" và trả về delta so với lần pre gần nhất.
    """
    ensure_user_exists(db, int(payload.user_id), role="student")

    answer_map = {a.question_id: a.answer for a in payload.answers}

    correct_count = 0
    for q in _DIAGNOSTIC_BANK:
        chosen = int(answer_map.get(q["id"], -1))
        if chosen == int(q["correct"]):
            correct_count += 1

    total = len(_DIAGNOSTIC_BANK)
    score_percent = int(round((correct_count / total) * 100)) if total else 0
    level = _level_from_score(score_percent)

    # Mastery theo nhóm topic (để so sánh pre/post nếu cần)
    mastery_by_topic, weak_topics = _mastery_from_diagnostic_answers(answer_map=answer_map, threshold=0.6)

    # Lấy pre-score gần nhất để so sánh
    pre = (
        db.query(DiagnosticAttempt)
        .filter(DiagnosticAttempt.user_id == payload.user_id, DiagnosticAttempt.stage == "pre")
        .order_by(DiagnosticAttempt.created_at.desc())
        .first()
    )
    pre_score = int(pre.score_percent) if pre else None
    delta = (score_percent - pre_score) if pre_score is not None else None

    # Lưu attempt post
    attempt = DiagnosticAttempt(
        user_id=payload.user_id,
        stage="post",
        score_percent=score_percent,
        correct_count=correct_count,
        total=total,
        level=level,
        answers_json=[{"question_id": a.question_id, "answer": a.answer} for a in payload.answers],
        mastery_json={
            "by_topic": mastery_by_topic,
            "weak_topics": weak_topics,
            "total_percent": score_percent,
        },
    )
    db.add(attempt)

    # Cập nhật mastery overall_post để tiện query nhanh (không bắt buộc)
    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == payload.user_id).first()
    if profile:
        mastery = dict(profile.mastery_json or {})
        mastery["overall_post"] = score_percent / 100.0
        profile.mastery_json = mastery

    db.commit()
    db.refresh(attempt)

    out = FinalResultData(
        attempt_id=attempt.id,
        stage="post",
        user_id=payload.user_id,
        score_percent=score_percent,
        correct_count=correct_count,
        total=total,
        level=level,
        pre_score_percent=pre_score,
        delta_score=delta,
    ).model_dump()

    return {"request_id": request.state.request_id, "data": out, "error": None}


@router.get("/profile/{user_id}")
def get_profile(request: Request, user_id: int, db: Session = Depends(get_db)):
    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found. Run /profile/diagnostic first.")

    out = LearnerProfileData(
        user_id=profile.user_id,
        level=profile.level,  # stored as string
        mastery={k: float(v) for k, v in (profile.mastery_json or {}).items()},
    ).model_dump()

    return {"request_id": request.state.request_id, "data": out, "error": None}


@router.get("/profile/{user_id}/next")
def recommend_next(request: Request, user_id: int, topic: str, db: Session = Depends(get_db)):
    """Simple adaptive rule based on mastery(topic)."""
    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    t = (topic or "").strip().lower()
    mastery_map = profile.mastery_json or {}
    mastery = float(mastery_map.get(t, 0.0))

    if mastery < 0.4:
        lvl = "beginner"
        reason = "Mastery còn thấp (<0.4) → nên ôn kiến thức nền và làm quiz dễ hơn."
    elif mastery < 0.7:
        lvl = "intermediate"
        reason = "Mastery mức trung bình (0.4–0.7) → tăng dần độ khó để củng cố."
    else:
        lvl = "advanced"
        reason = "Mastery cao (>=0.7) → chuyển sang bài vận dụng/tình huống."

    out = NextRecommendationData(topic=t, recommended_level=lvl, mastery=mastery, reason=reason).model_dump()
    return {"request_id": request.state.request_id, "data": out, "error": None}


@router.get("/v1/students/{userId}/level")
def student_level(request: Request, userId: int, db: Session = Depends(get_db)):
    latest_diag = (
        db.query(DiagnosticAttempt)
        .filter(DiagnosticAttempt.user_id == int(userId), DiagnosticAttempt.stage == "pre")
        .order_by(DiagnosticAttempt.created_at.desc())
        .first()
    )

    score = None
    if latest_diag:
        score = int(getattr(latest_diag, "score_percent", 0) or 0)
    else:
        latest_attempt = (
            db.query(Attempt)
            .join(QuizSet, QuizSet.id == Attempt.quiz_set_id)
            .filter(Attempt.user_id == int(userId), QuizSet.kind == "diagnostic_pre")
            .order_by(Attempt.created_at.desc())
            .first()
        )
        if latest_attempt:
            score = int(getattr(latest_attempt, "score_percent", 0) or 0)

    if score is None:
        raise HTTPException(status_code=404, detail="Diagnostic attempt not found")

    level = classify_student_level(score)
    return {"request_id": request.state.request_id, "data": level, "error": None}


@router.get("/profile/{user_id}/learning-path")
def learning_path(
    request: Request,
    user_id: int,
    threshold: float = 0.6,
    top_k: int = 3,
    max_modules: int = 6,
    with_plan: int = 1,
    days: int = 7,
    minutes_per_day: int = 35,
    save_plan: int = 0,
    db: Session = Depends(get_db),
):
    """Trả về "tài liệu học tập" dựa trên nội dung đã kiểm tra ở bài test đầu vào.

    UX theo yêu cầu:
    - Chỉ tập trung vào các topic yếu trong *diagnostic_pre* (không mở rộng/"củng cố" mọi phần).
    - Không trả danh sách chunk tham khảo; chỉ trả `lesson_md` (tài liệu học tập).
    """
    ensure_user_exists(db, int(user_id), role="student")

    # Ưu tiên dùng kết quả bài test đầu vào (diagnostic_pre)
    diag = (
        db.query(DiagnosticAttempt)
        .filter(DiagnosticAttempt.user_id == user_id, DiagnosticAttempt.stage == "pre")
        .order_by(DiagnosticAttempt.created_at.desc())
        .first()
    )

    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == user_id).first()
    if not profile:
        profile = LearnerProfile(user_id=user_id, level="beginner", mastery_json={})
        db.add(profile)
        db.commit()
        db.refresh(profile)

    mastery_by_topic: dict[str, float] = {}
    weak_topics: list[str] = []
    note: str | None = None
    level = profile.level

    if diag and isinstance(diag.mastery_json, dict):
        mj = diag.mastery_json or {}
        by_topic = mj.get("by_topic") or {}
        if isinstance(by_topic, dict):
            try:
                mastery_by_topic = {str(k): float(v) for k, v in by_topic.items()}
            except Exception:
                mastery_by_topic = {}

        wt = mj.get("weak_topics")
        if isinstance(wt, list):
            weak_topics = [str(x) for x in wt]
        else:
            weak_topics = [t for t, v in mastery_by_topic.items() if float(v) < float(threshold)]

        # Backward-compat: diagnostic_pre endpoint (MCQ bank) previously didn't fill mastery_json.
        # If mastery_by_topic is empty but we have answers_json, compute by-topic mastery now.
        if not mastery_by_topic and isinstance(diag.answers_json, list) and diag.answers_json:
            amap: dict[int, int] = {}
            for a in diag.answers_json:
                try:
                    qid = int(a.get("question_id"))
                except Exception:
                    continue
                # Some attempts store `answer`, some store `answer_index`.
                raw = a.get("answer")
                if raw is None:
                    raw = a.get("answer_index")
                try:
                    amap[qid] = int(raw)
                except Exception:
                    amap[qid] = -1

            if amap:
                mastery_by_topic, weak_topics = _mastery_from_diagnostic_answers(
                    answer_map=amap, threshold=float(threshold)
                )
                # Persist so next calls are fast and consistent.
                try:
                    mj2 = dict(mj)
                    mj2["by_topic"] = mastery_by_topic
                    mj2["weak_topics"] = weak_topics
                    mj2.setdefault("total_percent", int(diag.score_percent or 0))
                    diag.mastery_json = mj2
                    db.commit()
                except Exception:
                    db.rollback()

        # Nếu không có topic yếu → không ép tạo module, nhưng trả note để UI giải thích rõ.
        if not weak_topics:
            note = (
                f"Bạn đã đạt ngưỡng mastery ≥ {threshold:.2f} ở tất cả nhóm trong bài đầu vào. "
                "Bạn có thể chuyển sang luyện quiz theo topic bạn muốn, hoặc làm post-test để đo tiến bộ."
            )

        level = (diag.level or level)
    else:
        # Nếu chưa có record DiagnosticAttempt (thường do tự luận chưa chấm),
        # vẫn có thể lấy dữ liệu từ Attempt gần nhất của quiz_set.kind=diagnostic_pre.
        latest_attempt = (
            db.query(Attempt)
            .join(QuizSet, Attempt.quiz_set_id == QuizSet.id)
            .filter(Attempt.user_id == user_id, QuizSet.kind == "diagnostic_pre")
            .order_by(Attempt.created_at.desc())
            .first()
        )

        if latest_attempt:
            by_topic: dict[str, list[int]] = {}
            for it in (latest_attempt.breakdown_json or []):
                topic = str(it.get("topic") or "").strip() or "tài liệu"
                if it.get("type") != "mcq":
                    # Essay chưa chấm thì bỏ qua để tránh sai lệch.
                    continue
                total = 1
                earned = 1 if bool(it.get("is_correct")) else 0
                if topic not in by_topic:
                    by_topic[topic] = [0, 0]
                by_topic[topic][0] += earned
                by_topic[topic][1] += total

            mastery_by_topic = {
                t: (float(earned) / float(total) if total else 0.0)
                for t, (earned, total) in by_topic.items()
            }
            weak_topics = [t for t, v in mastery_by_topic.items() if float(v) < float(threshold)]
        else:
            # Theo yêu cầu: learning path chỉ dựa trên bài test đầu vào.
            # Nếu chưa làm diagnostic_pre thì trả rỗng (UI sẽ hiển thị hướng dẫn làm bài đầu vào).
            mastery_by_topic = {}
            weak_topics = []
            note = "Bạn chưa làm bài test đầu vào. Hãy vào mục Diagnostic để làm bài trước, rồi quay lại Learning Path."

    # Chủ đề giáo viên giao (nếu pre-test là bài giáo viên tạo)
    assigned_topic: str | None = None
    try:
        if diag and isinstance(diag.mastery_json, dict):
            assigned_topic = (diag.mastery_json or {}).get("teacher_topic") or None
        if not assigned_topic and diag and getattr(diag, "assessment_id", None):
            qs = db.query(QuizSet).filter(QuizSet.id == diag.assessment_id).first()
            if qs and (qs.topic or '').strip():
                assigned_topic = qs.topic.strip()
    except Exception:
        assigned_topic = None

    # Nếu không có DiagnosticAttempt (essay chưa chấm), nhưng có Attempt gần nhất
    if not assigned_topic:
        try:
            latest_attempt2 = (
                db.query(Attempt)
                .join(QuizSet, Attempt.quiz_set_id == QuizSet.id)
                .filter(Attempt.user_id == user_id, QuizSet.kind == "diagnostic_pre")
                .order_by(Attempt.created_at.desc())
                .first()
            )
            if latest_attempt2:
                qs2 = db.query(QuizSet).filter(QuizSet.id == latest_attempt2.quiz_set_id).first()
                if qs2 and (qs2.topic or '').strip():
                    assigned_topic = qs2.topic.strip()
        except Exception:
            assigned_topic = assigned_topic

    # assigned_mastery: best-effort score for the assigned topic (if any).
    # We DO NOT collapse mastery_by_topic anymore (to keep Learning Path personalized per inferred topics).
    assigned_mastery: float | None = None
    if assigned_topic and mastery_by_topic:
        if assigned_topic in mastery_by_topic:
            try:
                assigned_mastery = float(mastery_by_topic.get(assigned_topic) or 0.0)
            except Exception:
                assigned_mastery = None
        else:
            # case-insensitive match, else average
            try:
                lower_map = {str(k).lower(): k for k in mastery_by_topic.keys()}
                k0 = lower_map.get(str(assigned_topic).lower())
                if k0 is not None:
                    assigned_mastery = float(mastery_by_topic.get(k0) or 0.0)
                else:
                    assigned_mastery = float(sum(float(v) for v in mastery_by_topic.values()) / float(len(mastery_by_topic)))
            except Exception:
                assigned_mastery = None

    def rec_level(m: float) -> str:
        if m < 0.4:
            return "beginner"
        if m < 0.7:
            return "intermediate"
        return "advanced"

    # Sort weak topics (most weak first) and cap to avoid overwhelming the UI.
    weak_topics = list(dict.fromkeys([t for t in weak_topics if t]))
    weak_topics.sort(key=lambda t: mastery_by_topic.get(t, 0.0))

    if max_modules is not None:
        try:
            max_m = int(max_modules)
        except Exception:
            max_m = 6
        max_m = max(0, min(12, max_m))
        weak_topics = weak_topics[:max_m]

    # Topic-specific query hints (improves retrieval relevance)
    topic_query_hint = {
        "Python cơ bản": "Python kiểu dữ liệu, venv, pip, import, lỗi thường gặp.",
        "Web/API (HTTP + FastAPI + CORS)": "HTTP methods, idempotent, REST, FastAPI @app.post, CORSMiddleware, request/response.",
        "Database (SQL + Index)": "SQL SELECT, WHERE, JOIN, index, query optimization.",
        "DevOps/Config (.env + Docker Compose)": ".env environment variables, docker compose services, ports, volumes, depends_on.",
        "RAG & Vector DB": "RAG retrieval, embedding, chunking, FAISS, Chroma, vector similarity, sources citation.",
        "Learning analytics & Profiling": "mastery update rule, logging attempts, score tracking, level thresholds.",
    }

    modules = []
    for t in weak_topics:
        m = float(mastery_by_topic.get(t, 0.0) or 0.0)
        lvl = rec_level(m)

        # Query tập trung học tập (không yêu cầu bám nguyên văn, tránh match lan man)
        hint = topic_query_hint.get(t, "")
        query = f"{t}. {hint} Giải thích khái niệm, ví dụ ngắn, lỗi thường gặp, bài tập tự luyện."

        try:
            doc_ids = auto_document_ids_for_query(db, (assigned_topic or t or query), preferred_user_id=settings.DEFAULT_TEACHER_ID, max_docs=2)
            filters = {'document_ids': doc_ids} if doc_ids else {}
            rag = retrieve_and_log(db, query=query, top_k=max(int(top_k) * 4, 12), filters=filters)
        except Exception:
            rag = {"chunks": []}

        picked = _select_relevant_chunks(t, (rag.get("chunks") or []), limit=max(int(top_k) * 2, 8))

        # Theo yêu cầu: không trả "tài liệu tham khảo" dạng chunk. Chỉ dùng chunk để sinh lesson_md.
        sources: list[LearningMaterial] = []

        # Tài liệu học tập: ưu tiên LLM (nếu có), nếu không thì tạo offline (template)
        lesson_md = None
        lmode = (settings.LESSON_GEN_MODE or "auto").strip().lower()
        if lmode in {"auto", "llm"} and llm_available():
            packed = pack_chunks(picked, max_chunks=min(3, max(1, int(top_k))), max_chars_per_chunk=700, max_total_chars=2400)
            if packed:
                sys = (
                    "Bạn là trợ giảng. Hãy viết tài liệu học tập ngắn gọn, rõ ràng, thực dụng. "
                    "Quan trọng: KHÔNG dùng một khung sẵn cứng nhắc. Hãy tự chọn cấu trúc phù hợp với nội dung trong evidence_chunks "
                    "(khái niệm, quy trình, công thức, ví dụ, lỗi thường gặp...). "
                    "Kết thúc bằng 2–4 câu tự kiểm tra liên quan trực tiếp tới nội dung. "
                    "Không chép nguyên văn, và KHÔNG nhắc tới chunk_id hay tên chunk trong đầu ra."
                )
                user = {
                    "topic": t,
                    "recommended_level": lvl,
                    "mastery": m,
                    "evidence_chunks": packed,
                    "output_format": {"lesson_md": "markdown text"},
                }
                try:
                    resp = chat_json(
                        messages=[
                            {"role": "system", "content": sys},
                            {"role": "user", "content": __import__("json").dumps(user, ensure_ascii=False)},
                        ],
                        temperature=0.25,
                        max_tokens=900,
                    )
                    if isinstance(resp, dict):
                        lesson_md = (resp.get("lesson_md") or "").strip() or None
                except Exception:
                    lesson_md = None

        if not lesson_md:
            # Offline fallback: vẫn trả về "tài liệu học tập" thay vì danh sách chunk rời rạc
            lesson_md = _offline_lesson(t, lvl, m, picked)

        goal = f"Ôn đúng phần đã kiểm tra ở đầu vào: {t} (tập trung khái niệm + ví dụ + lỗi thường gặp)."

        modules.append(
            LearningModule(
                topic=t,
                recommended_level=lvl,
                mastery=m,
                goal=goal,
                lesson_md=lesson_md,
                materials=sources,
                evidence_chunk_ids=[int(x.get("chunk_id")) for x in (picked or []) if isinstance(x, dict) and x.get("chunk_id") is not None][:8],

                quiz_recommendation={
                    "topic": t,
                    "level": lvl,
                    "question_count": 5,
                    "rule": "Nếu quiz < 60%: học lại phần này; 60–85%: luyện tiếp; >85%: tăng độ khó.",
                    "steps": [
                        "Đọc tài liệu học tập (5–10 phút)",
                        "Tự trả lời 3 câu tự kiểm tra", 
                        "Bấm 'Luyện quiz' để làm 5 câu theo level gợi ý",
                        "Nếu <60% thì học lại và làm lại quiz",
                    ],
                },
            )
        )

    # Teacher-style daily plan (optional)
    teacher_plan = None
    try:
        if int(with_plan or 0) != 0:
            from app.services.learning_plan_service import build_teacher_learning_plan

            teacher_plan = build_teacher_learning_plan(
                db,
                user_id=int(user_id),
                level=str(level),
                assigned_topic=assigned_topic,
                modules=modules,
                days=int(days or 7),
                minutes_per_day=int(minutes_per_day or 35),
            )

            # Optionally persist the plan so task completion & homework grades can be saved.
            if teacher_plan and int(save_plan or 0) != 0:
                try:
                    from app.services.learning_plan_storage_service import save_teacher_plan

                    row = save_teacher_plan(
                        db,
                        user_id=int(user_id),
                        teacher_id=None,
                        assigned_topic=assigned_topic,
                        level=str(level),
                        days_total=int(days or 7),
                        minutes_per_day=int(minutes_per_day or 35),
                        teacher_plan=teacher_plan.model_dump(),
                    )
                    teacher_plan.plan_id = int(row.id)
                except Exception:
                    # non-fatal
                    pass
    except Exception:
        teacher_plan = None
    data = LearningPathData(
        user_id=user_id,
        level=level,
        assigned_topic=assigned_topic,
        assigned_mastery=assigned_mastery,
        topic_mastery=mastery_by_topic,
        weak_topics=weak_topics,
        modules=modules,
        teacher_plan=teacher_plan,
        note=note,
    )
    return {"request_id": request.state.request_id, "data": data.model_dump(), "error": None}
