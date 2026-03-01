from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.api.routes.health import router as health_router
from app.api.routes.documents import router as documents_router
from app.api.routes.rag import router as rag_router
from app.api.routes.quiz import router as quiz_router
from app.api.routes.tutor import router as tutor_router
from app.api.routes.agent import router as agent_router
from app.api.routes.adaptive import router as adaptive_router
from app.api.routes.retention import router as retention_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.profile import router as profile_router
from app.api.routes.homework import router as homework_router
from app.api.routes.learning_plans import router as learning_plans_router
from app.api.routes.evaluation import router as evaluation_router
from app.api.routes.assessments import router as assessments_router, teacher_router as teacher_assessments_router
from app.api.routes.llm import router as llm_router
from app.api.routes.classrooms import router as classrooms_router
from app.api.routes.exams import router as exams_router
from app.api.routes.lms import router as lms_router
from app.api.routes.admin import router as admin_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.auth import router as auth_router
from app.db.session import SessionLocal
from app.models.user import User
from app.services import vector_store


logger = logging.getLogger("app.request")
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)


def envelope(request_id: str, data: Any = None, error: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"request_id": request_id, "data": data, "error": error}


class InMemoryTokenBucket:
    def __init__(self, rate_per_minute: int):
        self.rate = max(1, int(rate_per_minute))
        self._buckets: dict[str, dict[str, float]] = {}

    def allow(self, key: str, rate_per_minute: int | None = None) -> bool:
        if rate_per_minute is not None:
            self.rate = max(1, int(rate_per_minute))
        now = time.monotonic()
        bucket = self._buckets.get(key)
        if bucket is None:
            self._buckets[key] = {"tokens": float(self.rate - 1), "ts": now}
            return True

        refill_per_sec = self.rate / 60.0
        elapsed = max(0.0, now - bucket["ts"])
        bucket["tokens"] = min(float(self.rate), bucket["tokens"] + elapsed * refill_per_sec)
        bucket["ts"] = now
        if bucket["tokens"] < 1.0:
            return False
        bucket["tokens"] -= 1.0
        return True


rate_limiter = InMemoryTokenBucket(settings.RATE_LIMIT_REQUESTS_PER_MINUTE)


app = FastAPI(
    title=settings.APP_NAME,
    version="0.3.0",
)
def _include_api_routers(fastapi_app: FastAPI, auth_enabled: bool) -> None:
    fastapi_app.include_router(health_router, prefix="/api")
    fastapi_app.include_router(documents_router, prefix="/api")
    fastapi_app.include_router(rag_router, prefix="/api")
    fastapi_app.include_router(quiz_router, prefix="/api")
    fastapi_app.include_router(tutor_router, prefix="/api")
    fastapi_app.include_router(agent_router, prefix="/api")
    fastapi_app.include_router(adaptive_router, prefix="/api")
    fastapi_app.include_router(retention_router, prefix="/api")
    fastapi_app.include_router(analytics_router, prefix="/api")
    fastapi_app.include_router(jobs_router, prefix="/api")
    fastapi_app.include_router(llm_router, prefix="/api")
    fastapi_app.include_router(classrooms_router, prefix="/api")
    fastapi_app.include_router(exams_router, prefix="/api")
    fastapi_app.include_router(lms_router, prefix="/api")
    fastapi_app.include_router(profile_router, prefix="/api")
    fastapi_app.include_router(homework_router, prefix="/api")
    fastapi_app.include_router(learning_plans_router, prefix="/api")
    fastapi_app.include_router(evaluation_router, prefix="/api")
    fastapi_app.include_router(assessments_router, prefix="/api")
    fastapi_app.include_router(teacher_assessments_router, prefix="/api")
    fastapi_app.include_router(admin_router, prefix="/api")
    fastapi_app.include_router(notifications_router, prefix="/api")
    if auth_enabled:
        fastapi_app.include_router(auth_router, prefix="/api")


def create_app(auth_enabled: Optional[bool] = None) -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.3.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _include_api_routers(app, settings.AUTH_ENABLED if auth_enabled is None else auth_enabled)
    return app


app = create_app()


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = req_id
    start = time.perf_counter()

    max_upload_bytes = int(settings.MAX_UPLOAD_MB) * 1024 * 1024
    content_type = (request.headers.get("content-type") or "").lower()
    content_length = request.headers.get("content-length")
    if content_type.startswith("multipart/form-data") and content_length:
        try:
            if int(content_length) > max_upload_bytes:
                return JSONResponse(
                    status_code=413,
                    content=envelope(
                        request_id=req_id,
                        data=None,
                        error={
                            "code": "PAYLOAD_TOO_LARGE",
                            "message": f"Upload exceeds {settings.MAX_UPLOAD_MB}MB limit",
                        },
                    ),
                )
        except ValueError:
            pass

    heavy_paths = {"/api/tutor/chat", "/api/v1/tutor/chat", "/api/rag/search", "/api/rag/corrective_search"}
    if request.url.path in heavy_paths:
        client_key = request.client.host if request.client else "unknown"
        bucket_key = f"{request.url.path}:{client_key}"
        if not rate_limiter.allow(bucket_key, settings.RATE_LIMIT_REQUESTS_PER_MINUTE):
            return JSONResponse(
                status_code=429,
                content=envelope(
                    request_id=req_id,
                    data=None,
                    error={
                        "code": "RATE_LIMITED",
                        "message": "Too many requests, please retry later.",
                    },
                ),
            )

    response = await call_next(request)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Request-ID"] = req_id
    logger.info(
        json.dumps(
            {
                "event": "request",
                "request_id": req_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
            },
            ensure_ascii=False,
        )
    )
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    detail = exc.detail
    # Preserve structured error details when provided (e.g., NEED_CLEAN_TEXT).
    if isinstance(detail, dict):
        code = str(detail.get("code") or "HTTP_ERROR")
        message = detail.get("message") or detail.get("reason") or str(detail)
        error = {"code": code, "message": message, "details": detail}
    else:
        error = {"code": "HTTP_ERROR", "message": str(detail)}

    return JSONResponse(
        status_code=exc.status_code,
        content=envelope(
            request_id=req_id,
            data=None,
            error=error,
        ),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=422,
        content=envelope(
            request_id=req_id,
            data=None,
            error={
                "code": "VALIDATION_ERROR",
                "message": "Invalid request",
                "details": {"errors": exc.errors()},
            },
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.exception(
        json.dumps(
            {
                "event": "unhandled_exception",
                "request_id": req_id,
                "path": request.url.path,
                "method": request.method,
            },
            ensure_ascii=False,
        )
    )
    message = "Internal server error"
    if settings.ENV.lower() not in {"prod", "production"}:
        message = str(exc)
    return JSONResponse(
        status_code=500,
        content=envelope(
            request_id=req_id,
            data=None,
            error={"code": "INTERNAL_ERROR", "message": message},
        ),
    )


@app.on_event("startup")
def bootstrap_demo_user():
    """Create demo users/classroom (safe to run repeatedly).

    Mode A UX expects:
      - Teacher: user_id=1
      - Students: user_id=2,3,...
    """
    vector_store.load_if_exists()  # load FAISS index if present
    db = SessionLocal()
    try:
        # Ensure teacher id=1
        t = db.query(User).filter(User.id == 1).first()
        if not t:
            t = User(id=1, email="teacher1@demo.local", full_name="Teacher 1", role="teacher", is_active=True)
            db.add(t)
            db.commit()
        else:
            changed = False
            if getattr(t, "role", "") != "teacher":
                t.role = "teacher"
                changed = True
            if not getattr(t, "email", None):
                t.email = "teacher1@demo.local"
                changed = True
            if changed:
                db.commit()

        # Ensure demo students exist (one teacher, one class, many students)
        try:
            from app.services.user_service import ensure_user_exists

            for sid in range(2, 11):
                ensure_user_exists(db, sid, role="student")
        except Exception:
            pass

        # Optional: create a demo classroom if none
        try:
            from app.models.classroom import Classroom, ClassroomMember

            c = db.query(Classroom).order_by(Classroom.created_at.desc()).first()
            if not c:
                c = Classroom(teacher_id=1, name="Lớp Demo", join_code="DEMO123")
                db.add(c)
                db.commit()
                db.refresh(c)

            # Join demo students into the demo class (idempotent)
            for sid in range(2, 11):
                exists = (
                    db.query(ClassroomMember)
                    .filter(ClassroomMember.classroom_id == int(c.id), ClassroomMember.user_id == int(sid))
                    .first()
                )
                if not exists:
                    db.add(ClassroomMember(classroom_id=int(c.id), user_id=int(sid)))
            db.commit()
        except Exception:
            pass
    finally:
        db.close()

