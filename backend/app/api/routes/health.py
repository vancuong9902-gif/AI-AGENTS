from fastapi import APIRouter, Response

from app.services import vector_store
from app.infra.queue import is_async_enabled

try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
except Exception:  # pragma: no cover
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4"

    def generate_latest() -> bytes:
        return b"# prometheus_client not installed\n"


router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok", "vector": vector_store.status(), "async_queue": {"enabled": bool(is_async_enabled())}}


@router.get("/health/ready")
def ready():
    return {"status": "ready"}


@router.get("/metrics", include_in_schema=False)
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
