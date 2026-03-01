from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional

from app.schemas.orchestrator_contract import OrchestratorResponse


_MOJIBAKE_PATTERNS = (
    "Ã",
    "Ä",
    "�",
    "â€œ",
    "â€",
    "ðŸ",
)


def _has_mojibake(text: str) -> bool:
    raw = str(text or "")
    if not raw:
        return False
    if any(p in raw for p in _MOJIBAKE_PATTERNS):
        return True
    # Dense non-word punctuation is a common sign of broken OCR extraction.
    junk_ratio = len(re.findall(r"[^\w\sÀ-ỹ]", raw, flags=re.UNICODE)) / max(1, len(raw))
    return junk_ratio > 0.35


def needs_clean_text(excerpts: Iterable[str]) -> bool:
    parts = [str(x or "") for x in excerpts]
    if not parts:
        return True
    empty_ratio = sum(1 for x in parts if len(x.strip()) < 20) / max(1, len(parts))
    if empty_ratio >= 0.6:
        return True
    bad_ratio = sum(1 for x in parts if _has_mojibake(x)) / max(1, len(parts))
    return bad_ratio >= 0.3


def make_orchestrator_response(
    *,
    action: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    next_steps: Optional[Iterable[str]] = None,
    status: str = "OK",
) -> Dict[str, Any]:
    payload = OrchestratorResponse(
        status=str(status or "OK").upper(),
        action=str(action or "respond"),
        message=" ".join(str(message or "").split())[:500],
        data=dict(data or {}),
        next_steps=[str(x).strip() for x in (next_steps or []) if str(x).strip()],
    )
    return payload.model_dump()


def make_need_clean_text_response(action: str = "validate_input") -> Dict[str, Any]:
    return make_orchestrator_response(
        status="NEED_CLEAN_TEXT",
        action=action,
        message="Phát hiện văn bản OCR/font lỗi nên chưa thể tạo nội dung bám sát SGK.",
        data={
            "reason": "text_quality_low_or_mojibake",
            "required": ["PDF có text layer", ".docx sạch dấu tiếng Việt"],
        },
        next_steps=[
            "Upload lại PDF có text layer hoặc file .docx.",
            "Nếu dùng scan, hãy OCR lại để text đọc được và đúng dấu.",
        ],
    )
