from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager
from collections import deque
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    http_exception_handler as fastapi_http_exception_handler,
    request_validation_exception_handler as fastapi_request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.security import get_password_hash
from app.core.logging import configure_logging
from app.core.observability import setup_observability
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
from app.api.routes.session import router as session_router
from app.api.routes.ai_smart_lms import router as ai_smart_lms_router
from app.api.routes.mvp import router as mvp_router
from app.learning_engine.presentation.router import router as teacher_ai_router
from app.db.session import SessionLocal
from app.models.user import User
from app.services import vector_store


configure_logging()
logger = logging.getLogger("app.request")


def envelope(request_id: str, data: Any = None, error: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"request_id": request_id, "data": data, "error": error}


class _RedisRateLimiter:
    def __init__(self, redis_url: str, rate_per_minute: int) -> None:
        self._rate = max(1, int(rate_per_minute))
        self._client = None
        self._fallback_buckets: dict[str, deque[float]] = {}
        self._fallback_lock = threading.Lock()
        try:
            import redis as _redis

            c = _redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=1)
            c.ping()
            self._client = c
        except Exception:
            logger.warning("Redis unavailable – rate limiter falling back to in-memory mode")

    def _allow_fallback(self, key: str, capacity: int) -> bool:
        now = time.time()
        with self._fallback_lock:
            bucket = self._fallback_buckets.setdefault(key, deque())
            while bucket and bucket[0] <= now - 60:
                bucket.popleft()
            if len(bucket) >= capacity:
                return False
            bucket.append(now)
            return True

    def allow(self, key: str, rate_per_minute: int | None = None) -> bool:
        capacity = max(1, int(rate_per_minute)) if rate_per_minute else self._rate
        if self._client is None:
            return self._allow_fallback(key, capacity)
        now = time.time()
        rkey = f"rl:{key}"
        try:
            pipe = self._client.pipeline()
            pipe.zremrangebyscore(rkey, 0, now - 60)
            pipe.zcard(rkey)
            pipe.zadd(rkey, {f"{now:.6f}": now})
            pipe.expire(rkey, 65)
            results = pipe.execute()
            return results[1] < capacity
        except Exception:
            return True


rate_limiter = _RedisRateLimiter(settings.REDIS_URL, settings.RATE_LIMIT_REQUESTS_PER_MINUTE)

_DOCS_INTERNAL_PATH_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi.json",
    "/docs/oauth2-redirect",
    "/api/v1/docs",
    "/api/v1/redoc",
    "/api/v1/openapi.json",
)


def _is_internal_docs_path(path: str) -> bool:
    return path.startswith(_DOCS_INTERNAL_PATH_PREFIXES)


def _include_api_routers(fastapi_app: FastAPI, auth_enabled: bool) -> None:
    fastapi_app.include_router(health_router, prefix="/api")
    fastapi_app.include_router(health_router)
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
    fastapi_app.include_router(teacher_ai_router, prefix="/api/v2")
    if auth_enabled:
        fastapi_app.include_router(auth_router, prefix="/api")
    fastapi_app.include_router(session_router, prefix="/api")
    fastapi_app.include_router(ai_smart_lms_router, prefix="/api")
    fastapi_app.include_router(mvp_router, prefix="/api")


def _log_registered_routes(fastapi_app: FastAPI) -> None:
    route_lines: list[str] = []
    for route in fastapi_app.routes:
        methods = getattr(route, "methods", None)
        if not methods:
            continue
        route_lines.append(f"{','.join(sorted(methods)):<20} {route.path}")

    logger.info("Registered routes:\n%s", "\n".join(sorted(route_lines)))


def _resolve_cors_origins() -> list[str]:
    origin = (settings.FRONTEND_ORIGIN or "").strip()
    if origin:
        return [origin]
    return [o for o in settings.BACKEND_CORS_ORIGINS if o != "*"]


def _seed_admin_user() -> None:
    db = SessionLocal()
    try:
        admin_email = (settings.ADMIN_EMAIL or "admin@demo.local").strip()
        existing = db.query(User).filter(User.email == admin_email).first()
        if existing:
            changed = False
            if existing.role != "admin":
                existing.role = "admin"
                changed = True
            if not getattr(existing, "password_hash", None):
                existing.password_hash = get_password_hash(settings.ADMIN_PASSWORD)
                changed = True
            if changed:
                db.add(existing)
                db.commit()
            return

        db.add(User(email=admin_email, full_name="System Admin", role="admin", password_hash=get_password_hash(settings.ADMIN_PASSWORD), is_active=True))
        db.commit()
    finally:
        db.close()


def _bootstrap_demo_users() -> None:
    """Create demo users/classroom (safe to run repeatedly).

    Mode A UX expects:
      - Teacher: user_id=1
      - Students: user_id=2,3,...
    """
    db = SessionLocal()
    try:
        # Ensure teacher id=1
        demo_password_hash = get_password_hash("password")
        t = db.query(User).filter(User.id == 1).first()
        if not t:
            t = User(
                id=1,
                email="teacher1@demo.local",
                full_name="Teacher 1",
                role="teacher",
                is_active=True,
                password_hash=demo_password_hash,
            )
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
            if not getattr(t, "password_hash", None):
                t.password_hash = demo_password_hash
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


@asynccontextmanager
async def _lifespan(app: FastAPI):
    vector_store.load_if_exists()
    _seed_admin_user()
    if settings.ENV.lower() == "dev" and settings.DEMO_SEED:
        _bootstrap_demo_users()
    if not settings.AUTH_ENABLED and settings.ENV.lower() not in {"prod", "production"}:
        logger.warning("⚠️ AUTH_ENABLED=false – Set true before deploying to production!")
    _log_registered_routes(app)
    yield


def create_app(auth_enabled: Optional[bool] = None) -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.4.0",
        lifespan=_lifespan,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @app.get("/api/v1/openapi.json", include_in_schema=False)
    def openapi_legacy_alias() -> dict[str, Any]:
        return app.openapi()

    @app.get("/api/v1/docs", include_in_schema=False)
    def docs_legacy_alias():
        return get_swagger_ui_html(
            openapi_url="/openapi.json",
            title=f"{settings.APP_NAME} - Swagger UI",
        )

    @app.get("/api/v1/redoc", include_in_schema=False)
    def redoc_legacy_alias():
        return get_redoc_html(
            openapi_url="/openapi.json",
            title=f"{settings.APP_NAME} - ReDoc",
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_resolve_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _include_api_routers(app, settings.AUTH_ENABLED if auth_enabled is None else auth_enabled)
    setup_observability(app)

    @app.get("/")
    def root() -> dict[str, str]:
        return {"message": "API running"}

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
    upload_methods = {"POST", "PUT", "PATCH"}
    is_body_upload = request.method in upload_methods and (
        content_type.startswith("multipart/form-data")
        or content_type.startswith("application/octet-stream")
        or content_type.startswith("application/json")
    )
    if is_body_upload and content_length:
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
            resp_429 = JSONResponse(
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
            resp_429.headers["Retry-After"] = "60"
            return resp_429

    mvp_upload_paths = {"/api/mvp/courses/upload", "/api/mvp/courses"}
    if request.url.path in mvp_upload_paths and request.method == "POST":
        client_key = request.client.host if request.client else "unknown"
        bucket_key = f"mvp_upload:{client_key}"
        if not rate_limiter.allow(bucket_key, 10):
            return JSONResponse(
                status_code=429,
                content=envelope(
                    request_id=req_id,
                    data=None,
                    error={
                        "code": "RATE_LIMITED",
                        "message": "Upload limit exceeded. Please wait before uploading again.",
                    },
                ),
            )

    try:
        response = await call_next(request)
    except Exception:
        if _is_internal_docs_path(request.url.path):
            raise
        logger.exception("Unhandled exception in request pipeline", exc_info=True)
        response = JSONResponse(
            status_code=500,
            content=envelope(
                request_id=req_id,
                data=None,
                error={"code": "INTERNAL_ERROR", "message": "Internal server error"},
            ),
        )
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Request-ID"] = req_id
    if request.method == "GET" and response.status_code == 200:
        response.headers.setdefault("Cache-Control", "public, max-age=30")
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


@app.middleware("http")
async def _security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if "server" in response.headers:
        del response.headers["server"]
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if _is_internal_docs_path(request.url.path):
        return await fastapi_http_exception_handler(request, exc)

    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    is_production = settings.ENV.lower() in {"prod", "production"}

    detail = exc.detail
    # Preserve structured error details when provided (e.g., NEED_CLEAN_TEXT).
    if isinstance(detail, dict):
        code = str(detail.get("code") or "HTTP_ERROR")
        message = detail.get("message") or detail.get("reason") or str(detail)
        if is_production and exc.status_code >= 500:
            message = "Internal server error"
        error = {"code": code, "message": message, "details": detail}
    else:
        message = str(detail)
        if is_production and exc.status_code >= 500:
            message = "Internal server error"
        error = {"code": "HTTP_ERROR", "message": message}

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
    if _is_internal_docs_path(request.url.path):
        return await fastapi_request_validation_exception_handler(request, exc)

    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.warning(
        json.dumps(
            {
                "event": "validation_error",
                "request_id": req_id,
                "path": request.url.path,
                "method": request.method,
                "errors": exc.errors(),
            },
            ensure_ascii=False,
        )
    )
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
    return JSONResponse(
        status_code=500,
        content=envelope(
            request_id=req_id,
            data=None,
            error={"code": "INTERNAL_ERROR", "message": "Internal server error"},
        ),
    )
