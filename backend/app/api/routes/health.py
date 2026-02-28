from fastapi import APIRouter

from app.services import vector_store
from app.infra.queue import is_async_enabled


router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok", "vector": vector_store.status(), "async_queue": {"enabled": bool(is_async_enabled())}}
