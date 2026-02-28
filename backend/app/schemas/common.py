from __future__ import annotations

from typing import Any, Optional, Dict
from pydantic import BaseModel


class ErrorOut(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class Envelope(BaseModel):
    request_id: str
    data: Optional[Any] = None
    error: Optional[ErrorOut] = None
