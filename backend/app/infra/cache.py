from __future__ import annotations

import json
from typing import Any

from app.core.config import settings

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None  # type: ignore


def _get_client():
    if redis is None:
        return None
    try:
        return redis.Redis.from_url(str(settings.REDIS_URL), decode_responses=True)
    except Exception:
        return None


def get_json(key: str) -> dict[str, Any] | None:
    client = _get_client()
    if client is None:
        return None
    try:
        value = client.get(key)
        if not value:
            return None
        return json.loads(value)
    except Exception:
        return None


def set_json(key: str, payload: dict[str, Any], ttl_seconds: int = 120) -> bool:
    client = _get_client()
    if client is None:
        return False
    try:
        client.setex(key, max(1, int(ttl_seconds)), json.dumps(payload, ensure_ascii=False))
        return True
    except Exception:
        return False
