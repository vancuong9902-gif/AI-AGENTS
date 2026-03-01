from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.schemas.exam import ExamTemplateOut


_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "resources" / "exam_templates.json"


@lru_cache(maxsize=1)
def load_exam_templates() -> List[Dict[str, Any]]:
    """Load templates from bundled JSON.

    Note: cached in-process; restart server to pick up file changes.
    """
    if not _TEMPLATE_PATH.exists():
        return []
    data = json.loads(_TEMPLATE_PATH.read_text(encoding="utf-8"))
    templates = data.get("templates") if isinstance(data, dict) else None
    return templates if isinstance(templates, list) else []


def list_templates() -> List[ExamTemplateOut]:
    out: List[ExamTemplateOut] = []
    for t in load_exam_templates():
        try:
            out.append(ExamTemplateOut.model_validate(t))
        except Exception:
            # skip malformed templates
            continue
    return out


def get_template(template_id: str) -> Optional[ExamTemplateOut]:
    for t in list_templates():
        if t.template_id == template_id:
            return t
    return None


def template_to_assessment_counts(template: ExamTemplateOut) -> Dict[str, int]:
    """Map template sections -> (easy_count, medium_count, hard_count).

    Rules:
    - multiple_choice with explicit difficulty easy/medium/hard goes to that bucket
    - essay defaults to hard unless difficulty=medium
    - missing difficulty for multiple_choice defaults to easy (backward compatible)
    """
    easy = 0
    medium = 0
    hard = 0
    for sec in template.sections:
        difficulty = str(sec.difficulty or "").strip().lower()
        if sec.type == "multiple_choice":
            if difficulty == "hard":
                hard += int(sec.count)
            elif difficulty == "medium":
                medium += int(sec.count)
            else:
                easy += int(sec.count)
        elif sec.type == "essay":
            if difficulty == "medium":
                medium += int(sec.count)
            else:
                hard += int(sec.count)

    return {
        "easy_count": max(0, easy),
        "medium_count": max(0, medium),
        "hard_count": max(0, hard),
    }
