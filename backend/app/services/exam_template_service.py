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
    """Map template sections -> (easy_count, hard_count).

    Current system supports:
    - easy_count: number of MCQ
    - hard_count: number of essay
    """
    easy = 0
    hard = 0
    for sec in template.sections:
        if sec.type == "multiple_choice":
            easy += int(sec.count)
        elif sec.type == "essay":
            hard += int(sec.count)
    # Defensive: ensure non-negative
    return {"easy_count": max(0, easy), "hard_count": max(0, hard)}
