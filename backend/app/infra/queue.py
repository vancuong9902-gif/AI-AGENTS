from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from app.core.config import settings

try:
    import redis  # type: ignore
    from rq import Queue  # type: ignore
    from rq.job import Job  # type: ignore

    _RQ_AVAILABLE = True
except Exception:  # pragma: no cover
    redis = None  # type: ignore
    Queue = None  # type: ignore
    Job = None  # type: ignore
    _RQ_AVAILABLE = False


def is_async_enabled() -> bool:
    return bool(_RQ_AVAILABLE and getattr(settings, "ASYNC_QUEUE_ENABLED", False))


def get_redis_conn():
    if not _RQ_AVAILABLE or redis is None:
        raise RuntimeError("redis/rq not installed")
    url = str(getattr(settings, "REDIS_URL", "redis://localhost:6379/0"))
    return redis.Redis.from_url(url)


def get_queue(name: str = "default"):
    if not _RQ_AVAILABLE or Queue is None:
        raise RuntimeError("redis/rq not installed")
    conn = get_redis_conn()
    return Queue(name, connection=conn, default_timeout=int(getattr(settings, "RQ_DEFAULT_TIMEOUT_SEC", 1800)))


def enqueue(fn: Callable[..., Any], *args: Any, queue_name: str = "default", **kwargs: Any) -> Dict[str, Any]:
    """Enqueue a background job.

    Returns a dict with job_id and status.
    If async is disabled, runs synchronously and returns a pseudo-job result.
    """
    if not is_async_enabled():
        # sync fallback
        out = fn(*args, **kwargs)
        return {"job_id": None, "queued": False, "sync_executed": True, "result": out}

    q = get_queue(queue_name)
    job = q.enqueue(fn, *args, **kwargs)
    return {"job_id": str(job.id), "queued": True, "sync_executed": False}


def fetch_job(job_id: str):
    if not is_async_enabled():
        raise RuntimeError("async queue disabled")
    conn = get_redis_conn()
    return Job.fetch(job_id, connection=conn)
