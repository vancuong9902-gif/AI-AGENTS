from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentMessage:
    sender: str
    recipient: str
    payload: dict[str, Any]
    timestamp: datetime
