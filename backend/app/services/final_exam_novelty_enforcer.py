from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, List, Tuple


def _normalize_stem(text: str) -> str:
    s = unicodedata.normalize("NFKC", str(text or "")).strip().lower()
    s = re.sub(r"^\s*(câu|cau|question)\s*\d+\s*[:.)-]?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _flatten_history(history_stems: Dict[str, List[str]]) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for source, stems in (history_stems or {}).items():
        if not isinstance(stems, list):
            continue
        for stem in stems:
            pairs.append((str(source), _normalize_stem(str(stem))))
    return pairs


def _similarity(a: str, b: str) -> float:
    return float(SequenceMatcher(None, a, b).ratio())


def enforce_final_exam_novelty(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        selected_topics = [str(t).strip() for t in (payload.get("selected_topics") or []) if str(t).strip()]
        required_diff = payload.get("difficulty") or {}
        candidate_questions = payload.get("candidate_questions") or []
        history_pairs = _flatten_history(payload.get("history_stems") or {})
        threshold = float(payload.get("similarity_threshold", 0.75))

        if not selected_topics or not isinstance(required_diff, dict):
            return {
                "status": "ERROR",
                "data": {
                    "novel_questions": [],
                    "removed_as_duplicate": [],
                    "coverage_report": {"by_topic": {}, "by_difficulty": {}},
                    "notes": ["Invalid selected_topics or difficulty config."],
                },
                "error": "INVALID_INPUT",
            }

        removed: List[Dict[str, Any]] = []
        novel: List[Dict[str, Any]] = []

        for q in candidate_questions:
            if not isinstance(q, dict):
                continue
            stem = _normalize_stem(str(q.get("stem") or ""))
            if not stem:
                removed.append(
                    {
                        "id": str(q.get("id") or ""),
                        "reason": "invalid_stem",
                        "match_preview": "",
                        "similarity": 1.0,
                    }
                )
                continue

            best_src = ""
            best_match = ""
            best_score = 0.0
            for src, old_stem in history_pairs:
                if not old_stem:
                    continue
                score = _similarity(stem, old_stem)
                if score > best_score:
                    best_score = score
                    best_src = src
                    best_match = old_stem

            if best_score >= threshold:
                removed.append(
                    {
                        "id": str(q.get("id") or ""),
                        "reason": f"similar_to_{best_src}",
                        "match_preview": best_match[:200],
                        "similarity": round(best_score, 4),
                    }
                )
            else:
                novel.append(q)

        by_topic: Dict[str, int] = {}
        by_difficulty: Dict[str, int] = {}
        for q in novel:
            topic = str(q.get("topic") or "").strip()
            diff = str(q.get("difficulty") or "").strip().lower()
            if topic:
                by_topic[topic] = by_topic.get(topic, 0) + 1
            if diff:
                by_difficulty[diff] = by_difficulty.get(diff, 0) + 1

        notes: List[str] = []
        need_regen = False

        for t in selected_topics:
            if by_topic.get(t, 0) <= 0:
                notes.append(f"Missing topic coverage: {t}")
                need_regen = True

        for diff, need in required_diff.items():
            if int(by_difficulty.get(diff, 0)) != int(need or 0):
                notes.append(
                    f"Difficulty mismatch for {diff}: expected {int(need or 0)}, got {int(by_difficulty.get(diff, 0))}"
                )
                need_regen = True

        # Optional strict grounding mode: if regeneration is needed but no textbook materials are supplied,
        # caller can request NEED_MORE_MATERIALS instead of REGENERATE.
        if bool(payload.get("require_book_grounding")) and need_regen and not payload.get("book_materials"):
            notes.append("Cannot verify explanation grounding to textbook evidence. Provide clean textbook extracts.")
            return {
                "status": "NEED_MORE_MATERIALS",
                "data": {
                    "novel_questions": novel,
                    "removed_as_duplicate": removed,
                    "coverage_report": {"by_topic": by_topic, "by_difficulty": by_difficulty},
                    "notes": notes,
                },
                "error": None,
            }

        status = "REGENERATE" if (removed or need_regen) else "OK"
        return {
            "status": status,
            "data": {
                "novel_questions": novel,
                "removed_as_duplicate": removed,
                "coverage_report": {"by_topic": by_topic, "by_difficulty": by_difficulty},
                "notes": notes,
            },
            "error": None,
        }
    except Exception as exc:
        return {
            "status": "ERROR",
            "data": {
                "novel_questions": [],
                "removed_as_duplicate": [],
                "coverage_report": {"by_topic": {}, "by_difficulty": {}},
                "notes": [],
            },
            "error": str(exc),
        }
