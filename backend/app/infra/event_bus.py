from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import redis


class RedisEventBus:
    def __init__(self, url: str = "redis://localhost:6379"):
        self.client = redis.Redis.from_url(url, decode_responses=True)
        self.stream_key = "ai_agent:events"

    def publish(self, event_type: str, payload: dict[str, Any], user_id: str | None = None) -> str:
        event_id = str(uuid.uuid4())
        event = {
            "event_id": event_id,
            "type": event_type,
            "payload": json.dumps(payload),
            "user_id": str(user_id or ""),
            "timestamp": datetime.utcnow().isoformat(),
            "status": "pending",
        }
        self.client.xadd(self.stream_key, event)
        return event_id

    def consume(self, consumer_group: str, consumer_name: str, count: int = 10):
        try:
            events = self.client.xreadgroup(
                consumer_group,
                consumer_name,
                {self.stream_key: ">"},
                count=count,
                block=1000,
            )
            return events
        except redis.ResponseError:
            self.client.xgroup_create(self.stream_key, consumer_group, id="0", mkstream=True)
            return []

    def ack(self, consumer_group: str, message_id: str):
        self.client.xack(self.stream_key, consumer_group, message_id)

    def pending_count(self) -> int:
        try:
            return int(self.client.xlen(self.stream_key))
        except Exception:
            return 0
