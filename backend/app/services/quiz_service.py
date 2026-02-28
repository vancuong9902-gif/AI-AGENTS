from __future__ import annotations

import random
import json
import re

from typing import Any, Dict, List, Tuple, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from fastapi import HTTPException

from app.core.config import settings
from app.schemas.quiz import QuizGenerateRequest, QuizSubmitRequest
from app.models.quiz_set import QuizSet
from app.models.question import Question
from app.models.attempt import Attempt
from app.models.learner_profile import LearnerProfile
from app.models.document_topic import DocumentTopic
from app.models.document_chunk import DocumentChunk
from app.services.rag_service import retrieve_and_log, auto_document_ids_for_query
from app.services.corrective_rag import corrective_retrieve_and_log
from app.services.text_quality import filter_chunks_by_quality
from app.services.user_service import ensure_user_exists
from app.services.llm_service import llm_available, chat_json, pack_chunks
from app.services.language_service import preferred_question_language
from app.services.bloom import (
    BLOOM_LEVELS,
    allocate_bloom_counts,
    get_level_distribution,
    infer_bloom_level,
    normalize_bloom_level,
)

# Keep topic ranges tight in DB (for clean topic display) and expand *only when generating quizzes*.
from app.services.topic_service import ensure_topic_chunk_ranges_ready_for_quiz, clean_text_for_generation


def _snippet(text: str, max_len: int = 110) -> str:
    s = " ".join(str(text).split())
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"


def _is_codey(text: str) -> bool:
    """Heuristic: detect code-heavy snippets to avoid turning them into quiz options."""
    t = (text or "").strip()
    if not t:
        return True
    # Many symbols / operators -> likely code
    sym = sum(ch in "{}[]();:=<>/*+-_\\|`~" for ch in t)
    if sym / max(1, len(t)) > 0.08:
        return True
    # Common code tokens
    code_markers = ["def ", "class ", "import ", "#include", "printf(", "console.", "scipy.", "numpy", "plt.", "=>", "==", "!="]
    tl = t.lower()
    if any(m in tl for m in code_markers):
        return True
    # Too few letters -> not natural language
    letters = sum(ch.isalpha() for ch in t)
    if letters / max(1, len(t)) < 0.55:
        return True
    return False


_VI_STOP = {
    # Vietnamese stopwords / generic tokens
    "và","là","của","cho","trong","một","các","được","với","khi","này","đó","từ","đến",
    "the","and","for","with","from","that","this","are","is","to","in","on","of","a","an",
    # too-generic Vietnamese terms that make bad blanks/options
    "thông","qua","dấu","ngoặc","phần","tử","giá","trị","mỗi","khác","nhau","bằng","sau","đây",
    # generic question words / meta terms that become nonsense options
    "lý","do","mục","tiêu","ý","tưởng","nghĩa","điều","cách","phát","biểu","chọn",
    "python","lập","trình",
}


# Term prefixes that often show up due to chunk-boundary splits (not real "concept terms")
_BAD_TERM_PREFIXES = (
    "mục tiêu",
    "lý do",
    "ý tưởng",
    "điều",
    "cách",
    "phát biểu",
    "chọn",
    "ví dụ",
    "chú ý",
    "lưu ý",
)


_SENT_SPLIT = re.compile(r"(?<=[\.\?\!])\s+")


def _pick_keyword(sentence: str, topic: str) -> str | None:
    """Pick a reasonable 'blank' keyword from a sentence."""
    topic_tokens = set(re.findall(r"[\w]+", (topic or "").lower()))
    toks = re.findall(r"[A-Za-zÀ-ỹà-ỹ0-9_]+", sentence)
    cands = []
    for tok in toks:
        low = tok.lower()
        if len(low) < 4:
            continue
        if low in _VI_STOP:
            continue
        if low in topic_tokens:
            continue
        if low.isdigit():
            continue
        cands.append(tok)
    if not cands:
        return None
    # Prefer longer / more specific tokens
    cands.sort(key=lambda x: (len(x), x.lower()), reverse=True)
    return cands[0]


def _mask_first(sentence: str, keyword: str) -> str:
    pat = re.compile(rf"\b{re.escape(keyword)}\b", flags=re.IGNORECASE)
    return pat.sub("____", sentence, count=1)


def _find_chunk_id(chunks: List[Dict[str, Any]], pattern: str) -> int | None:
    """Return the first chunk_id whose text matches the regex pattern (case-insensitive)."""
    try:
        rx = re.compile(pattern, flags=re.IGNORECASE)
    except re.error:
        return None
    for c in chunks:
        txt = c.get("text") or ""
        if rx.search(txt):
            cid = c.get("chunk_id")
            try:
                cid_int = int(cid)
                if cid_int > 0:
                    return cid_int
            except Exception:
                continue
    return None


def _mcq(
    stem: str,
    correct: str,
    wrongs: List[str],
    chunk_id: int,
    explanation: str,
    *,
    bloom_level: str = "understand",
) -> Dict[str, Any]:
    """Build a MCQ dict in the format expected by Question model."""
    options = [correct] + list(wrongs)
    options = options[:4]
    while len(options) < 4:
        options.append("Không có đáp án đúng")
    random.shuffle(options)
    correct_index = options.index(correct)
    return {
        "type": "mcq",
        "bloom_level": normalize_bloom_level(bloom_level),
        "stem": stem,
        "options": options,
        "correct_index": correct_index,
        "explanation": explanation,
        "sources": [{"chunk_id": int(chunk_id)}],
    }


def _ensure_topic_in_stem(stem: str, topic: str) -> str:
    s = (stem or "").strip()
    t = (topic or "tài liệu").strip()
    if not t:
        t = "tài liệu"
    # We rely on Assessment code to infer topic by quotes in stem.
    if f"'{t}'" in s or f"\"{t}\"" in s or f"“{t}”" in s:
        return s
    if s.lower().startswith("chủ đề"):
        return f"Chủ đề '{t}': {s}"
    return f"Chủ đề '{t}': {s}"


# ===== Standalone teacher-like MCQ enforcement =====
_DOC_REF_RE = re.compile(
    r"(?i)\b(?:theo|dựa\s*trên|căn\s*cứ|trích|trích\s*dẫn|ở\s*trên|trong)\s+"
    r"(?:tài\s*liệu|văn\s*bản|đoạn|bài|chương|mục|trang|hình|bảng)\b"
    r"|\bchunk\b|\bevidence\b|\bevidence_chunks\b|\bpdf\b|\bocr\b"
)

def _normalize_ws_qs(text: str) -> str:
    return " ".join(str(text or "").split()).strip()

def _has_ngram_overlap_qs(text: str, chunk_text: str, n_words: int = 12) -> bool:
    t = _normalize_ws_qs(text).lower()
    c = _normalize_ws_qs(chunk_text).lower()
    if not t or not c:
        return False
    words = t.split()
    if len(words) < n_words:
        return False
    for i in range(0, len(words) - n_words + 1):
        phrase = " ".join(words[i:i + n_words])
        if phrase and phrase in c:
            return True
    return False

def _needs_standalone_rewrite_mcq(q: Dict[str, Any], packed_chunks: List[Dict[str, Any]]) -> bool:
    stem = _normalize_ws_qs(q.get("stem") or "")
    if not stem:
        return True
    if _DOC_REF_RE.search(stem):
        return True
    for c in (packed_chunks or []):
        if _has_ngram_overlap_qs(stem, c.get("text") or "", n_words=12):
            return True
    return False

def _rewrite_mcq_standalone_with_llm(*, topic: str, level: str, packed_chunks: List[Dict[str, Any]], q: Dict[str, Any], language: Dict[str, Any] | None = None) -> Optional[Dict[str, Any]]:
    if not llm_available():
        return None

    lang = language or {"code": "vi", "name": "Vietnamese"}

    system = f"""Bạn là GIẢNG VIÊN ra đề. Viết lại 1 câu hỏi trắc nghiệm để:
- CÂU HỎI ĐỘC LẬP: học sinh KHÔNG cần đọc tài liệu gốc vẫn trả lời được.
- Tài liệu chỉ là 'chuẩn kiến thức': bám sát kiến thức trong evidence_chunks nhưng KHÔNG hỏi dạng đọc-hiểu theo câu chữ.
- Không trích nguyên văn; không tham chiếu 'theo tài liệu/đoạn/chương/trang/hình/bảng'.
- Ưu tiên: định nghĩa theo bản chất, so sánh/đối chiếu, tình huống thực tiễn, lỗi thường gặp.
- 4 lựa chọn A/B/C/D, chỉ 1 đáp án đúng; distractors hợp lý.
- explanation 2–4 câu.
- sources: 1–2 chunk_id.
- NGÔN NGỮ ĐẦU RA: {lang.get('name','Vietnamese')}. (Toàn bộ stem/options/explanation phải dùng ngôn ngữ này.)
Chỉ xuất JSON hợp lệ."""

    user = {
        "topic": topic,
        "level": level,
        "evidence_chunks": packed_chunks,
        "draft_question": {
            "bloom_level": q.get("bloom_level"),
            "stem": q.get("stem"),
            "options": q.get("options"),
            "correct_index": q.get("correct_index"),
            "explanation": q.get("explanation"),
            "sources": q.get("sources"),
        },
        "language": lang,
        "output_format": {
            "question": {
                "type": "mcq",
                "bloom_level": "apply",
                "stem": "string",
                "options": ["A", "B", "C", "D"],
                "correct_index": 0,
                "explanation": "giải thích ngắn gọn tại sao đáp án đúng (2-3 câu)",
                "hint": "gợi ý nếu học sinh chọn sai (1-2 câu, không tiết lộ đáp án)",
                "related_concept": "tên khái niệm/phần trong sách cần xem lại",
                "sources": [{"chunk_id": 123}],
            }
        },
    }

    try:
        data = chat_json(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.35,
            max_tokens=900,
        )
    except Exception:
        return None

    if not isinstance(data, dict):
        return None
    out = data.get("question")
    if not isinstance(out, dict):
        return None
    out["type"] = "mcq"
    return out

def enforce_standalone_mcqs(*, topic: str, level: str, chunks: List[Dict[str, Any]], questions: List[Dict[str, Any]], max_rewrites: int = 4) -> List[Dict[str, Any]]:
    """Ensure MCQs are standalone (no document references) and not copied verbatim."""
    if not questions:
        return []

    packed = pack_chunks(chunks, max_chunks=8) or []
    lang = preferred_question_language(packed)
    out: List[Dict[str, Any]] = []
    rewrites = 0

    for q in (questions or []):
        if not isinstance(q, dict):
            continue
        if (q.get("type") or "").lower() != "mcq":
            out.append(q)
            continue

        qq = dict(q)

        # Light cleanup first
        stem = _normalize_ws_qs(qq.get("stem") or "")
        stem = re.sub(r"(?i)^(?:theo|dựa\s*trên)\s+(?:tài\s*liệu|văn\s*bản)\s*[:\-]?\s*", "", stem).strip()
        stem = re.sub(r"(?i)\b(trong|ở)\s+(?:đoạn|bài|chương|mục|trang|hình|bảng)\s*\d+\b", "", stem).strip()
        qq["stem"] = stem

        if max_rewrites and llm_available() and rewrites < int(max_rewrites) and _needs_standalone_rewrite_mcq(qq, packed):
            rewritten = _rewrite_mcq_standalone_with_llm(topic=topic, level=level, packed_chunks=packed, q=qq, language=lang)
            if isinstance(rewritten, dict) and rewritten.get("stem"):
                qq = rewritten
                rewrites += 1

        out.append(qq)

    return out


def _generate_mcq_with_llm(
    topic: str,
    level: str,
    question_count: int,
    chunks: List[Dict[str, Any]],
    extra_system_hint: str | None = None,
    excluded_stems: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """LLM-based MCQ generator (high quality + grounded to teacher materials).

    Goals:
    - Diverse question styles (khái niệm / phân biệt / tình huống / lỗi thường gặp)
    - Strictly grounded in retrieved evidence chunks (mỗi câu có sources)
    - Clean 4-option MCQ with 1 correct answer

    Output is sanitized to avoid common demo issues:
    - Missing/duplicate options
    - Invalid correct_index
    - Missing topic hint in stem
    - Invalid sources (chunk_id not in packed excerpts)
    """
    mode = (settings.QUIZ_GEN_MODE or "auto").strip().lower()
    if mode == "offline" or not llm_available():
        return []

    packed = pack_chunks(chunks, max_chunks=8)
    if not packed:
        return []

    lang = preferred_question_language(packed)

    valid_ids = [int(c["chunk_id"]) for c in packed]

    def _tok(s: str) -> set[str]:
        s = (s or "").lower()
        return {w for w in re.findall(r"[\wÀ-ỹ]+", s) if len(w) >= 3}

    def _best_sources(text_hint: str, k: int = 2) -> List[Dict[str, int]]:
        hint = _tok(text_hint)
        scored = []
        for c in packed:
            cid = int(c.get("chunk_id"))
            ct = _tok(f"{c.get('title') or ''} {c.get('text') or ''}")
            score = len(hint & ct)
            scored.append((score, cid))
        scored.sort(reverse=True)
        picked = [cid for score, cid in scored if score > 0][:k]
        if not picked:
            picked = [valid_ids[0]]
        return [{"chunk_id": int(x)} for x in picked]
    # More explicit, higher-quality prompting
    system = f"""Bạn là GIẢNG VIÊN RA ĐỀ + Assessment Agent.
    Nhiệm vụ: tạo bộ câu hỏi kiểm tra dựa CHỈ trên ngữ liệu được cung cấp (CONTEXT/TOPIC).
    Không copy nguyên văn; phải diễn đạt lại đúng tinh thần SGK/giáo viên (rõ ràng, sư phạm).

    NGÔN NGỮ ĐẦU RA: {lang.get('name','Vietnamese')}.
    - Tất cả stem/options/explanation phải dùng đúng ngôn ngữ này.
    - Không trộn ngôn ngữ (trừ thuật ngữ chuyên ngành bắt buộc).

    PHONG CÁCH ĐỀ THI:
    - Viết giống đề thi tốt nghiệp THPT (Việt Nam): câu hỏi ngắn gọn, hỏi trọng tâm, một ý chính mỗi câu.
    - Ưu tiên cách hỏi quen thuộc: "Phát biểu nào sau đây đúng?", "Giải thích nào đúng nhất?", "Trong các lựa chọn sau, lựa chọn đúng là...".

    QUY TẮC CHỐNG "TÀI LIỆU PDF ẢNH/OCR LỖI":
    - Nếu CONTEXT bị rời rạc/đứt chữ/nhiều ký tự lỗi, hoặc thiếu thông tin để ra đề chắc chắn:
      => KHÔNG ĐƯỢC BỊA. Hãy trả về JSON với status="NEED_CLEAN_TEXT" và nêu reason ngắn + suggestion:
         "hãy upload file .docx hoặc pdf có text layer / bản copy text".
    - Chỉ khi CONTEXT đủ rõ mới sinh câu hỏi.

    CHẤT LƯỢNG CÂU HỎI:
    - Câu hỏi PHẢI ĐỘC LẬP (standalone): học sinh không cần mở/đọc tài liệu gốc vẫn làm được.
    - TUYỆT ĐỐI KHÔNG tham chiếu tài liệu: không nói "theo tài liệu", "trong đoạn/chương/trang/hình/bảng".
    - KHÔNG hỏi dạng đọc-hiểu theo câu chữ/chi tiết mặt chữ của tài liệu (tác giả, câu văn, số trang...).
      Thay vào đó: hỏi về bản chất khái niệm, điều kiện áp dụng, quy trình, so sánh, tình huống thực tiễn, lỗi thường gặp.
    - Ưu tiên câu hỏi hiểu bản chất, so sánh, tình huống, suy luận.
    - Tránh hỏi kiểu định nghĩa máy móc (trừ khi Bloom=remember và thật sự cần).
    - Mỗi câu phải rõ ràng, không mơ hồ, không lỗi chính tả.
    - Với MCQ: 4 lựa chọn A/B/C/D, chỉ 1 đáp án đúng.
    - Distractors (phương án sai) phải hợp lý, dễ gây nhầm lẫn theo lỗi thường gặp (không vô lý, không quá lộ).

    BLOOM & PHÂN BỔ:
    - Mỗi câu gắn bloom_level ∈ {"remember","understand","apply","analyze","evaluate","create"}.
    - Tạo theo phân bổ % và bloom_target_counts do INPUT cung cấp.
    - Câu ở mỗi nhóm Bloom PHẢI KHÁC NHAU (không hỏi lại cùng ý bằng cách đổi chữ).

    BÁM NGUỒN:
    - evidence_chunks chỉ dùng để đảm bảo kiến thức nằm trong phạm vi đã học.
    - Mỗi câu phải có sources: mảng các chunk_id lấy từ evidence_chunks.
    - Không bịa kiến thức mâu thuẫn với CONTEXT.

    ĐẦU RA:
    - Chỉ xuất JSON hợp lệ, không thêm giải thích ngoài JSON.
    - Nếu OK: {"status":"OK","questions":[...]}.
    - Nếu CONTEXT lỗi/thiếu: {"status":"NEED_CLEAN_TEXT","reason":"...","suggestion":"..."}.
    """

    if extra_system_hint:
        system = f"{system}\n\n{str(extra_system_hint).strip()}"

    if excluded_stems:
        blocked = [str(x or "").strip() for x in excluded_stems if str(x or "").strip()]
        blocked = blocked[:40]
        if blocked:
            blocked_payload = json.dumps(blocked, ensure_ascii=False)
            system = (
                f"{system}\n\n"
                "KHÔNG tạo câu hỏi giống/na ná với danh sách stem đã dùng trước đó. "
                "Nếu ý tưởng gần giống, hãy đổi ngữ cảnh, dữ kiện và cách hỏi hoàn toàn. "
                f"Danh sách stem cần tránh: {blocked_payload}"
            )

    # Desired mix by level (team rule) + Bloom distribution (6-level)
    mix_text = {
        "beginner": "60% nhận biết/ghi nhớ, 30% hiểu, 10% vận dụng nhẹ",
        "intermediate": "30% nhận biết, 50% vận dụng/phân tích, 20% so sánh/đánh giá",
        "advanced": "20% phân tích, 50% vận dụng tình huống, 30% đánh giá/thiết kế giải pháp",
    }.get((level or "").strip().lower(), "Phối hợp đa dạng mức độ")

    bloom_dist = get_level_distribution(level)
    bloom_counts = allocate_bloom_counts(int(question_count), bloom_dist)

    user = {
        "topic": topic,
        "level": level,
        "language": lang,
        "question_count": int(question_count),
        "difficulty_mix": mix_text,
        "bloom_levels": BLOOM_LEVELS,
        "bloom_distribution": bloom_dist,
        "bloom_target_counts": bloom_counts,
        "evidence_chunks": packed,
        "constraints": [
            "Stem 2–3 câu, tự đủ ngữ cảnh để trả lời. Không tham chiếu 'tài liệu/văn bản/đoạn/chương/mục/trang/hình/bảng'.",
            "Câu hỏi PHẢI ĐỘC LẬP (standalone): học sinh không cần mở tài liệu gốc vẫn làm được.",
            "Không trích nguyên văn quá 8 từ liên tiếp từ evidence_chunks; phải diễn đạt lại.",
            "Không hỏi kiểu định nghĩa máy móc; ưu tiên hiểu bản chất, phân biệt, so sánh, tình huống.",
            "Options đúng 4 lựa chọn, cùng dạng diễn đạt, không quá dài; không dùng 'Tất cả các đáp án', 'Cả A và B', 'Không có đáp án đúng'.",
            "Các phương án sai (distractors) phải hợp lý và dễ gây nhầm lẫn (sai vì thiếu/nhầm điều kiện, nhầm phạm vi...), tránh sai hiển nhiên.",
            "Chỉ 1 đáp án đúng và phải rõ ràng dựa trên evidence_chunks.",
            "Giải thích 2–4 câu: nêu vì sao đúng, và vì sao 1–2 lựa chọn sai (lỗi thường gặp).",
            "Mỗi câu phải có bloom_level thuộc: remember/understand/apply/analyze/evaluate/create.",
            "Tập câu hỏi phải bám sát bloom_target_counts (chênh lệch tối đa ±1 mỗi mức nếu bắt buộc).",
            "KHÔNG dùng các cụm từ/thuật ngữ: 'theo tài liệu', 'dựa trên tài liệu', 'trích', 'đoạn', 'chunk', 'evidence'.",
            "sources BẮT BUỘC là danh sách chunk_id (từ evidence_chunks) đã dùng làm bằng chứng; mỗi câu có ít nhất 1 chunk_id.",
            "Các câu phải đa dạng và PHÙ HỢP nội dung thật sự trong CONTEXT (không lặp một khung sẵn). Có thể hỏi khái niệm, phân biệt, quy trình/bước làm, công thức & ý nghĩa, tình huống áp dụng, nhận diện/sửa sai lầm...",
        ],
        "output_format": {
            "questions": [
                {
                    "bloom_level": "remember",
                    "stem": "string",
                    "options": ["A", "B", "C", "D"],
                    "correct_index": 0,
                    "explanation": "giải thích ngắn gọn tại sao đáp án đúng (2-3 câu)",
                    "hint": "gợi ý nếu học sinh chọn sai (1-2 câu, không tiết lộ đáp án)",
                    "related_concept": "tên khái niệm/phần trong sách cần xem lại",
                    "sources": [{"chunk_id": 123}],
                }
            ]
        },
    }

    try:
        data = chat_json(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.45,
            max_tokens=2400,
        )
    except Exception:
        return []

    # Respect OCR / low-signal contexts: do NOT hallucinate or fallback.
    if isinstance(data, dict) and str(data.get("status", "")).upper() == "NEED_CLEAN_TEXT":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "NEED_CLEAN_TEXT",
                "message": "CONTEXT không đủ rõ để sinh câu hỏi bám tài liệu.",
                "reason": data.get("reason") or data.get("message") or "CONTEXT bị rời rạc/ký tự lỗi hoặc thiếu thông tin chắc chắn.",
                "suggestion": data.get("suggestion") or "Hãy upload file .docx hoặc PDF có text layer / hoặc copy text của mục cần ra đề.",
            },
        )
    raw_qs = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(raw_qs, list):
        return []

    cleaned: List[Dict[str, Any]] = []
    for q in raw_qs:
        if not isinstance(q, dict):
            continue

        stem = " ".join(str(q.get("stem") or "").split())
        if not stem or len(stem) < 10:
            continue

        options = _sanitize_options(q.get("options"))
        if len(options) < 4:
            continue
        options = options[:4]
        if len({o.lower() for o in options}) < 4:
            continue

        # Ban common ambiguous patterns
        banned = ("tất cả", "cả a", "cả b", "không có đáp án")
        if any(any(b in o.lower() for b in banned) for o in options):
            continue

        try:
            ci = int(q.get("correct_index"))
        except Exception:
            continue
        if ci < 0 or ci > 3:
            continue

        explanation = " ".join(str(q.get("explanation") or "").split())
        hint = " ".join(str(q.get("hint") or "").split())
        related_concept = " ".join(str(q.get("related_concept") or "").split())
        sources = _coerce_sources(q.get("sources"), valid_ids)

        raw_bloom = q.get("bloom_level")
        if isinstance(raw_bloom, str) and raw_bloom.strip():
            bloom = normalize_bloom_level(raw_bloom)
        else:
            bloom = infer_bloom_level(f"{stem} {options[ci]} {explanation}", default="understand")

        # Enforce grounding: always ensure at least 1 source
        if not sources:
            sources = _best_sources(f"{stem} {options[ci]} {explanation}", k=2)

        cleaned.append(
            {
                "type": "mcq",
                "bloom_level": bloom,
                "stem": stem,
                "options": options,
                "correct_index": ci,
                "explanation": explanation,
                "hint": hint,
                "related_concept": related_concept,
                "sources": sources,
            }
        )
        if len(cleaned) >= int(question_count):
            break

    cleaned = enforce_standalone_mcqs(topic=topic, level=level, chunks=chunks, questions=cleaned, max_rewrites=4)
    return cleaned

def _sanitize_options(opts: Any) -> List[str]:
    out: List[str] = []
    for x in (opts or []):
        s = " ".join(str(x).split())
        if not s:
            continue
        out.append(s)
    # de-dup while preserving order
    seen = set()
    uniq = []
    for s in out:
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(s)
    return uniq


def _coerce_sources(raw: Any, valid_chunk_ids: List[int]) -> List[Dict[str, int]]:
    out: List[Dict[str, int]] = []
    if not raw:
        return out
    if isinstance(raw, dict):
        raw = [raw]
    for it in list(raw):
        cid = None
        if isinstance(it, dict):
            cid = it.get("chunk_id")
        else:
            cid = it
        try:
            cid = int(cid)
        except Exception:
            continue
        if cid in valid_chunk_ids:
            out.append({"chunk_id": cid})
    # keep max 2 sources
    return out[:2]


def _quiz_refine_enabled(
    *,
    questions: Optional[List[Dict[str, Any]]] = None,
    gen_mode: Optional[str] = None,
) -> bool:
    """Return True if we should run the LLM "editor" refine pass for MCQs.

    Settings:
    - QUIZ_LLM_REFINE: off | auto | always
      - off: never refine
      - auto: refine only when LLM is available AND we detect low-quality signals
      - always: refine whenever LLM is available
    """
    mode = (settings.QUIZ_LLM_REFINE or "auto").strip().lower()
    if mode == "off":
        return False
    if not llm_available():
        return False
    if mode == "always":
        return True

    # auto mode: only refine when needed (keeps cost stable)
    q = questions or []
    gm = (gen_mode or "").strip().lower()
    if gm == "offline":
        return True
    return _needs_refine(q)


def _needs_refine(questions: List[Dict[str, Any]]) -> bool:
    """Heuristic to detect low-quality MCQs (short answers, weak distractors, etc.)."""
    if not questions:
        return False
    for q in questions:
        try:
            stem = (q.get("stem") or "").strip()
            opts = q.get("options") or []
            exp = (q.get("explanation") or "").strip()
            if len(stem) < 18:
                return True
            if not isinstance(opts, list) or len(opts) != 4:
                return True
            if len({str(o).strip().lower() for o in opts if str(o).strip()}) < 4:
                return True
            if any(len(str(o).strip()) < 3 for o in opts):
                return True
            if any("không có đáp án" in str(o).lower() for o in opts):
                return True
            if len(exp) < 35:
                return True
            # Nonsense stems commonly produced by OCR noise
            if re.search(r"[\^\~\|]{2,}|�{2,}", stem):
                return True
        except Exception:
            return True
    return False


def _llm_refine_mcqs(
    *,
    topic: str,
    level: str,
    chunks: List[Dict[str, Any]],
    questions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Refine an existing MCQ set using an LLM "editor" pass.

    Input:
      - evidence chunks (ground truth)
      - draft questions (may be weak: short answers, bad distractors, unclear stems)

    Output:
      - improved questions: clearer stems, better distractors, consistent 4-option format,
        one correct answer, and a short pedagogical explanation.

    Safety/grounding:
      - Must cite sources with chunk_id from the provided evidence.
      - If the editor output is invalid, we fall back to the original questions.
    """
    if not questions:
        return []
    if not llm_available():
        return questions

    packed = pack_chunks(chunks, max_chunks=8)
    if not packed:
        return questions
    valid_ids = [int(c["chunk_id"]) for c in packed]

    # Limit cost
    max_n = int(getattr(settings, "QUIZ_LLM_REFINE_MAX_QUESTIONS", 20) or 20)
    max_n = max(1, min(max_n, len(questions)))
    draft = questions[:max_n]

    # Bloom target distribution (keep consistent)
    bloom_dist = get_level_distribution(level)
    bloom_counts = allocate_bloom_counts(int(max_n), bloom_dist)

    system = """Bạn là GIẢNG VIÊN ra đề kiêm BIÊN TẬP VIÊN câu hỏi.

PHONG CÁCH ĐỀ THI:
- Biên tập theo phong cách đề thi tốt nghiệp THPT (Việt Nam): ngắn gọn, rõ ràng, hỏi trọng tâm.
- Tránh văn phong kể lể; mỗi câu tập trung một ý.

Nhiệm vụ: CHỈ DỰA TRÊN CONTEXT (evidence_chunks) để BIÊN TẬP lại bộ câu hỏi trắc nghiệm nháp.

YÊU CẦU CHẤT LƯỢNG:
- Câu hỏi PHẢI ĐỘC LẬP (standalone): học sinh không cần đọc tài liệu gốc vẫn trả lời được.
- Viết câu hỏi giống giáo viên: rõ ràng, sư phạm, ưu tiên hiểu bản chất/so sánh/tình huống.
- Không copy nguyên văn; diễn đạt lại đúng tinh thần.
- 4 lựa chọn A/B/C/D, chỉ 1 đáp án đúng.
- Distractors phải hợp lý (sai do nhầm điều kiện/phạm vi/khái niệm), tránh sai hiển nhiên.
- Giải thích 2–4 câu: nêu vì sao đúng + vì sao 1–2 phương án sai.

RÀNG BUỘC:
- KHÔNG dùng kiến thức ngoài CONTEXT.
- Mỗi câu PHẢI có sources: danh sách chunk_id lấy từ evidence_chunks.
- Không được dùng các từ: "theo tài liệu", "trích", "đoạn", "chunk", "evidence".
- Giữ số lượng câu y hệt draft_questions (không thêm/bớt). Nếu câu nháp không đủ căn cứ, hãy viết lại câu khác có căn cứ trong CONTEXT.
- Bám bloom_target_counts (chênh lệch tối đa ±1 nếu bắt buộc).

ĐẦU RA: Chỉ xuất JSON hợp lệ.
Nếu OK: {"status":"OK","questions":[...]}
Nếu CONTEXT không đủ rõ: {"status":"NEED_CLEAN_TEXT","reason":"...","suggestion":"..."}
"""

    user = {
        "topic": topic,
        "level": level,
        "bloom_levels": BLOOM_LEVELS,
        "bloom_distribution": bloom_dist,
        "bloom_target_counts": bloom_counts,
        "evidence_chunks": packed,
        "draft_questions": [
            {
                "bloom_level": q.get("bloom_level"),
                "stem": q.get("stem"),
                "options": q.get("options"),
                "correct_index": q.get("correct_index"),
                "explanation": q.get("explanation"),
                "sources": q.get("sources"),
            }
            for q in draft
        ],
        "output_format": {
            "questions": [
                {
                    "bloom_level": "understand",
                    "stem": "string",
                    "options": ["A", "B", "C", "D"],
                    "correct_index": 0,
                    "explanation": "giải thích ngắn gọn tại sao đáp án đúng (2-3 câu)",
                    "hint": "gợi ý nếu học sinh chọn sai (1-2 câu, không tiết lộ đáp án)",
                    "related_concept": "tên khái niệm/phần trong sách cần xem lại",
                    "sources": [{"chunk_id": valid_ids[0]}],
                }
            ]
        },
    }

    try:
        data = chat_json(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.25,
            max_tokens=2200,
        )
    except Exception:
        return questions

    if isinstance(data, dict) and str(data.get("status", "")).upper() == "NEED_CLEAN_TEXT":
        # Do not hallucinate; keep the original drafts.
        return questions

    raw_qs = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(raw_qs, list) or not raw_qs:
        return questions

    def _tok(s: str) -> set[str]:
        s = (s or "").lower()
        return {w for w in re.findall(r"[\wÀ-ỹ]+", s) if len(w) >= 3}

    def _best_sources(text_hint: str, k: int = 2) -> List[Dict[str, int]]:
        hint = _tok(text_hint)
        scored = []
        for c in packed:
            cid = int(c.get("chunk_id"))
            ct = _tok(f"{c.get('title') or ''} {c.get('text') or ''}")
            score = len(hint & ct)
            scored.append((score, cid))
        scored.sort(reverse=True)
        picked = [cid for score, cid in scored if score > 0][:k]
        if not picked:
            picked = [valid_ids[0]]
        return [{"chunk_id": int(x)} for x in picked]

    cleaned: List[Dict[str, Any]] = []
    for q in raw_qs[:max_n]:
        if not isinstance(q, dict):
            continue

        stem = " ".join(str(q.get("stem") or "").split())
        if not stem or len(stem) < 12:
            continue

        options = _sanitize_options(q.get("options"))
        if len(options) < 4:
            continue
        options = options[:4]
        if len({o.lower() for o in options}) < 4:
            continue

        banned = ("tất cả", "cả a", "cả b", "không có đáp án")
        if any(any(b in o.lower() for b in banned) for o in options):
            continue

        try:
            ci = int(q.get("correct_index"))
        except Exception:
            continue
        if ci < 0 or ci > 3:
            continue

        explanation = " ".join(str(q.get("explanation") or "").split())
        hint = " ".join(str(q.get("hint") or "").split())
        related_concept = " ".join(str(q.get("related_concept") or "").split())
        sources = _coerce_sources(q.get("sources"), valid_ids)

        raw_bloom = q.get("bloom_level")
        bloom = normalize_bloom_level(raw_bloom) if isinstance(raw_bloom, str) and raw_bloom.strip() else infer_bloom_level(
            f"{stem} {options[ci]} {explanation}", default="understand"
        )

        if not sources:
            sources = _best_sources(f"{stem} {options[ci]} {explanation}", k=2)

        cleaned.append(
            {
                "type": "mcq",
                "bloom_level": bloom,
                "stem": stem,
                "options": options,
                "correct_index": ci,
                "explanation": explanation,
                "hint": hint,
                "related_concept": related_concept,
                "sources": sources,
            }
        )

    if not cleaned:
        return questions

    # If we lost items due to validation, fill from original drafts (best-effort)
    if len(cleaned) < max_n:
        for q in draft:
            if len(cleaned) >= max_n:
                break
            cleaned.append(q)

    # Preserve any tail questions that we didn't refine
    refined = cleaned[:max_n] + questions[max_n:]
    refined = enforce_standalone_mcqs(topic=topic, level=level, chunks=chunks, questions=refined, max_rewrites=2)
    return refined



_DEF_VI = re.compile(
    r"(?P<term>[A-Za-zÀ-ỹ0-9_\-\s]{3,60}?)\s+(?:là|được\s+gọi\s+là|được\s+định\s+nghĩa\s+là|nghĩa\s+là)\s+(?P<def>[^\.\!\?]{20,240})",
    flags=re.IGNORECASE,
)

_DEF_EN = re.compile(
    r"(?P<term>[A-Za-z][A-Za-z0-9_\-\s]{2,60}?)\s+(?:is|are|refers\s+to|means)\s+(?P<def>[^\.\!\?]{20,240})",
    flags=re.IGNORECASE,
)


# "X gồm/bao gồm ..." / "X includes/consists of ..." patterns
_INC_VI = re.compile(
    r"(?P<head>[A-Za-zÀ-ỹ0-9_\-\s]{3,80}?)\s+(?:gồm|bao\s+gồm|bao\s+gồm\s+các|gồm\s+các|có\s+các|bao\s+gồm\s*:|gồm\s*:|gồm\s+là)\s+(?P<items>[^\.\!\?]{12,240})",
    flags=re.IGNORECASE,
)

_INC_EN = re.compile(
    r"(?P<head>[A-Za-z][A-Za-z0-9_\-\s]{2,80}?)\s+(?:includes|consists\s+of|contains)\s+(?P<items>[^\.\!\?]{12,240})",
    flags=re.IGNORECASE,
)


def _mine_definitions(chunks: List[Dict[str, Any]]) -> List[Tuple[str, str, int]]:
    """Extract (term, definition, chunk_id) candidates from retrieved chunks.

    Non-LLM heuristic to create better MCQs across arbitrary topics.
    """
    out: List[Tuple[str, str, int]] = []
    for c in (chunks or []):
        chunk_id = int(c.get("chunk_id") or 0)
        if chunk_id <= 0:
            continue
        txt = " ".join((c.get("text") or "").split())
        if len(txt) < 80 or _is_codey(txt):
            continue

        sents = _SENT_SPLIT.split(txt) if _SENT_SPLIT.search(txt) else [txt]
        for sent in sents:
            sent = sent.strip()
            if not (40 <= len(sent) <= 280):
                continue
            if _is_codey(sent):
                continue

            m = _DEF_VI.search(sent) or _DEF_EN.search(sent)
            if not m:
                continue

            term = " ".join((m.group("term") or "").split()).strip("-–—:;,. ")
            definition = " ".join((m.group("def") or "").split()).strip("-–—:;,. ")
            if not term or not definition:
                continue

            # Heuristic filters to avoid garbage "terms" that are actually sentence fragments
            # produced by chunk-boundary splitting (e.g., "Mục tiêu ...", "Lý do ...").
            term_low = term.lower()
            if any(term_low.startswith(pfx) for pfx in _BAD_TERM_PREFIXES):
                continue
            # Too many words usually indicates we're capturing a clause, not a concept name.
            if len(term.split()) > 7:
                continue
            if len(term_low) < 4:
                continue
            if term_low in _VI_STOP:
                continue
            if any(x in term_low for x in ["đây", "này", "đó", "chúng ta", "bạn"]):
                continue
            # Avoid ultra-generic terms
            if term_low in {"hệ thống", "mô hình", "phương pháp", "giải pháp", "bài toán"}:
                continue

            out.append((term, definition, chunk_id))

    # Deduplicate by term (keep first)
    seen = set()
    uniq: List[Tuple[str, str, int]] = []
    for term, definition, cid in out:
        k = term.lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append((term, definition, cid))
    return uniq


def _split_items(text: str) -> List[str]:
    """Split an 'items' span into candidate list items (very lightweight)."""
    t = " ".join((text or "").split()).strip("-–—:;,. ")
    if not t:
        return []
    # Normalize separators
    t = t.replace(";", ",").replace("•", ",").replace("·", ",")
    # Common Vietnamese list joiners
    t = re.sub(r"\s+(?:và|hoặc)\s+", ", ", t, flags=re.IGNORECASE)
    parts = [p.strip("-–—:;,. ") for p in t.split(",")]
    items: List[str] = []
    for p in parts:
        if not p:
            continue
        if len(p) < 2 or len(p) > 80:
            continue
        if _is_codey(p):
            continue
        items.append(p)
    # Dedup
    seen: set[str] = set()
    out: List[str] = []
    for it in items:
        k = it.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def _mine_includes(chunks: List[Dict[str, Any]]) -> List[Tuple[str, List[str], int]]:
    """Extract (head, items[], chunk_id) from 'includes/bao gồm' style sentences."""
    out: List[Tuple[str, List[str], int]] = []
    for c in (chunks or []):
        cid = int(c.get("chunk_id") or 0)
        if cid <= 0:
            continue
        txt = " ".join((c.get("text") or "").split())
        if len(txt) < 80 or _is_codey(txt):
            continue
        sents = _SENT_SPLIT.split(txt) if _SENT_SPLIT.search(txt) else [txt]
        for sent in sents:
            sent = sent.strip()
            if not (50 <= len(sent) <= 320):
                continue
            if _is_codey(sent):
                continue
            m = _INC_VI.search(sent) or _INC_EN.search(sent)
            if not m:
                continue
            head = " ".join((m.group("head") or "").split()).strip("-–—:;,. ")
            items_raw = m.group("items") or ""
            items = _split_items(items_raw)
            if not head or len(head) < 3:
                continue
            if len(items) < 2:
                continue
            # avoid super-generic heads
            hl = head.lower()
            if hl in {"hệ thống", "mô hình", "phương pháp", "giải pháp"}:
                continue
            out.append((head, items[:8], cid))

    # Dedup by (head, items-set)
    seen: set[str] = set()
    uniq: List[Tuple[str, List[str], int]] = []
    for head, items, cid in out:
        k = head.lower() + "|" + "|".join(sorted([i.lower() for i in items]))
        if k in seen:
            continue
        seen.add(k)
        uniq.append((head, items, cid))
    return uniq


def _generate_definition_mcqs(topic: str, level: str, question_count: int, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Generate definitional MCQs mined from the retrieved chunks only (no hard-coded subject templates).

    We look for sentences like: "X là ..." / "X is ..." and then:
    - Ask about the meaning of a term (term comes from the document)
    - Provide 3 distractor definitions (also from the document)

    If we can't find enough distinct term-definition pairs to make single-correct MCQs, return [].
    """
    pairs = _mine_definitions(chunks)
    if len(pairs) < 4:
        return []

    # Keep definitions short to avoid looking like a copied paragraph.
    defs = [(_snippet(d, 120), term, cid) for term, d, cid in pairs]
    random.shuffle(defs)

    questions: List[Dict[str, Any]] = []
    for defn, term, cid in defs:
        other = [(_snippet(d, 140), t) for (d, t, _) in defs if t.lower() != term.lower()]
        if len(other) < 3:
            continue
        wrongs = [d for (d, _) in random.sample(other, 3)]

        # Keep stems natural; avoid doc-referential phrasing.
        lv = (level or "").strip().lower()
        if lv == "beginner":
            stem = f"Khái niệm '{term}' được hiểu đúng nhất là gì?"
        elif lv == "intermediate":
            stem = f"Mô tả nào phù hợp nhất với '{term}'?"
        else:
            stem = f"Phát biểu nào mô tả đúng nhất '{term}'?"

        bloom = "remember" if lv == "beginner" else "understand"

        questions.append(
            _mcq(
                stem=stem,
                correct=defn,
                wrongs=wrongs,
                chunk_id=cid,
                explanation=f"Mô tả đúng tương ứng với khái niệm '{term}'.",
                bloom_level=bloom,
            )
        )

        if len(questions) >= int(question_count):
            break

    return questions


def _generate_term_from_definition_mcqs(topic: str, level: str, question_count: int, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Generate MCQs that ask for the TERM given a description (definition).

    This avoids "fill-in-the-blank" and avoids doc-referential wording.
    Options are terms that all appear in retrieved chunks.
    """
    pairs = _mine_definitions(chunks)
    if len(pairs) < 4:
        return []

    # Build a term pool and a description pool
    # Keep the description short so it doesn't look like a copied paragraph.
    items = [(term, _snippet(defn, 90), cid) for (term, defn, cid) in pairs]
    random.shuffle(items)

    terms = [t for (t, _d, _cid) in items]
    questions: List[Dict[str, Any]] = []

    for term, defn, cid in items:
        others = [t for t in terms if t.lower() != term.lower()]
        if len(others) < 3:
            continue
        wrongs = random.sample(others, 3)

        lv = (level or "").strip().lower()
        if lv == "beginner":
            stem = f"Thuật ngữ nào phù hợp nhất với mô tả sau? {defn}"
        elif lv == "intermediate":
            stem = f"Mô tả sau đang nói đến khái niệm/thuật ngữ nào? {defn}"
        else:
            stem = f"Chọn thuật ngữ tương ứng chính xác nhất với mô tả: {defn}"

        bloom = "remember" if lv == "beginner" else "understand"

        questions.append(
            _mcq(
                stem=stem,
                correct=term,
                wrongs=wrongs,
                chunk_id=cid,
                explanation=f"Mô tả này khớp với thuật ngữ '{term}'.",
                bloom_level=bloom,
            )
        )
        if len(questions) >= int(question_count):
            break

    return questions


def _generate_includes_mcqs(topic: str, level: str, question_count: int, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Generate MCQs from "X gồm/bao gồm ..." style statements.

    This produces conceptual questions without quoting full sentences or referencing the document.
    """
    groups = _mine_includes(chunks)
    if not groups:
        return []

    random.shuffle(groups)
    questions: List[Dict[str, Any]] = []

    # Build a distractor pool from all items across groups (still document-only)
    all_items: List[str] = []
    for _head, items, _cid in groups:
        all_items.extend(items)
    # Dedup
    seen: set[str] = set()
    pool: List[str] = []
    for it in all_items:
        k = it.lower()
        if k in seen:
            continue
        seen.add(k)
        if _is_codey(it) or len(it) < 2 or len(it) > 80:
            continue
        pool.append(it)

    for head, items, cid in groups:
        if len(questions) >= int(question_count):
            break
        if len(items) < 2:
            continue

        correct = random.choice(items)
        wrong_cands = [x for x in pool if x.lower() != correct.lower() and x.lower() not in {i.lower() for i in items}]
        if len(wrong_cands) < 3:
            wrong_cands = [x for x in pool if x.lower() != correct.lower()]
        if len(wrong_cands) < 3:
            continue
        wrongs = random.sample(wrong_cands, 3)

        lv = (level or "").strip().lower()
        if lv == "beginner":
            stem = f"'{head}' bao gồm thành phần nào sau đây?"
        elif lv == "intermediate":
            stem = f"Thành phần nào là một phần của '{head}'?"
        else:
            stem = f"Chọn phương án thuộc tập thành phần của '{head}'."

        bloom = "remember" if lv == "beginner" else "understand"

        questions.append(
            _mcq(
                stem=stem,
                correct=correct,
                wrongs=wrongs,
                chunk_id=cid,
                explanation=f"'{correct}' là một thành phần được nêu trong nhóm '{head}'.",
                bloom_level=bloom,
            )
        )

    return questions


def _term_ok(term: str) -> bool:
    t = (term or "").strip()
    if not t:
        return False
    if len(t) < 3 or len(t) > 80:
        return False
    if re.fullmatch(r"\d+(?:[\.,]\d+)?", t):
        return False
    if t.lower() in _VI_STOP:
        return False
    if _is_codey(t):
        return False
    if len(t) <= 4 and t.isupper():
        return False
    return True


def _extract_term_pool(chunks: List[Dict[str, Any]], *, max_terms: int = 120) -> List[str]:
    """Extract candidate key terms from retrieved chunks (topic-agnostic, document-only).

    Sources for key terms:
    - Term mined from definition patterns (X là Y / X is Y)  -> often high-quality, multi-word
    - Frequent content tokens from chunk texts (filtered by stopwords)
    """
    freq: Dict[str, int] = {}
    surface: Dict[str, str] = {}

    # 1) Definition-mined terms first (boosted)
    for term, _defn, _cid in _mine_definitions(chunks):
        if not _term_ok(term):
            continue
        k = term.lower()
        surface.setdefault(k, term)
        freq[k] = freq.get(k, 0) + 5

    # 2) Frequent tokens
    rx_tok = re.compile(r"[A-Za-zÀ-ỹ][A-Za-zÀ-ỹ0-9_\-]{2,}")
    for c in (chunks or []):
        txt = (c.get("text") or "")
        if not txt:
            continue
        for tok in rx_tok.findall(txt):
            low = tok.lower()
            if low in _VI_STOP:
                continue
            if len(low) < 4:
                continue
            if low.isdigit():
                continue
            surface.setdefault(low, tok)
            freq[low] = freq.get(low, 0) + 1

    items = sorted(freq.items(), key=lambda kv: (kv[1], len(kv[0])), reverse=True)
    out: List[str] = []
    seen = set()
    for low, _f in items:
        term = surface.get(low, low)
        if term.lower() in seen:
            continue
        if not _term_ok(term):
            continue
        seen.add(term.lower())
        out.append(term)
        if len(out) >= int(max_terms):
            break
    return out


def _build_sentence_pool(topic: str, chunks: List[Dict[str, Any]]) -> List[Tuple[str, int, str]]:
    """Return list of (sentence, chunk_id, keyword) derived only from chunks."""
    pool: List[Tuple[str, int, str]] = []
    for c in (chunks or []):
        chunk_id = int(c.get("chunk_id") or 0)
        if chunk_id <= 0:
            continue
        txt = " ".join((c.get("text") or "").split())
        if len(txt) < 80 or _is_codey(txt):
            continue
        sents = _SENT_SPLIT.split(txt) if _SENT_SPLIT.search(txt) else [txt]
        for sent in sents:
            sent = sent.strip()
            if not (60 <= len(sent) <= 260):
                continue
            if _is_codey(sent):
                continue
            kw = _pick_keyword(sent, topic)
            if not kw or not _term_ok(kw):
                continue
            pool.append((sent, chunk_id, kw))
    return pool


def _pick_distractors(correct: str, term_pool: List[str], *, k: int = 3) -> List[str]:
    """Pick k distractors from term_pool, derived from the same retrieved document."""
    correct_low = (correct or "").lower()
    cands = []
    for t in (term_pool or []):
        tl = t.lower()
        if tl == correct_low:
            continue
        if not _term_ok(t):
            continue
        # avoid near-duplicates/substrings
        if correct_low in tl or tl in correct_low:
            continue
        cands.append(t)

    if len(cands) < k:
        cands = [t for t in (term_pool or []) if t.lower() != correct_low and _term_ok(t)]

    if len(cands) <= k:
        return cands[:k]
    return random.sample(cands, k=k)


def _generate_cloze_mcqs(topic: str, level: str, question_count: int, chunks: List[Dict[str, Any]], term_pool: List[str]) -> List[Dict[str, Any]]:
    """Generate fill-in-the-blank MCQs grounded to chunk sentences.

    - Correct answer is a keyword/token that appears in the sentence.
    - 3 distractors are selected from OTHER key terms found in the retrieved chunks,
      plus (if needed) additional tokens extracted from the same sentence.

    This stays document-only (no hard-coded subject templates / no generic distractors).
    """
    pool = _build_sentence_pool(topic, chunks)
    if not pool:
        return []

    term_pool2 = list(term_pool) if term_pool else []
    lowset = {t.lower() for t in term_pool2}

    # add keywords mined from sentences if missing
    for _sent, _cid, kw in pool:
        if kw and kw.lower() not in lowset and _term_ok(kw):
            term_pool2.append(kw)
            lowset.add(kw.lower())

    random.shuffle(pool)
    questions: List[Dict[str, Any]] = []
    used: set[str] = set()
    rx_tok_local = re.compile(r"[A-Za-zÀ-ỹ][A-Za-zÀ-ỹ0-9_\-]{2,}")

    for sent, chunk_id, kw in pool:
        if len(questions) >= int(question_count):
            break

        # Local distractor pool: global key-terms + tokens extracted from the same sentence
        local_pool = list(term_pool2)
        low_seen = {t.lower() for t in local_pool}
        for tok in rx_tok_local.findall(sent):
            if not _term_ok(tok):
                continue
            tl = tok.lower()
            if tl == kw.lower():
                continue
            if tl in low_seen:
                continue
            low_seen.add(tl)
            local_pool.append(tok)

        distractors = _pick_distractors(kw, local_pool, k=3)
        if len(distractors) < 3:
            continue

        # Avoid a "quoted excerpt" look. We still ground to the sentence, but do NOT present it as a citation.
        masked = _mask_first(sent, kw)
        stem = f"Chọn từ/cụm từ phù hợp nhất để hoàn chỉnh ý sau: {masked}"
        key = _norm_stem_for_dedupe(stem)
        if key in used:
            continue
        used.add(key)

        options = [kw] + distractors[:3]

        # ensure 4 unique
        uniq: List[str] = []
        seen: set[str] = set()
        for o in options:
            ol = o.lower()
            if ol in seen:
                continue
            seen.add(ol)
            uniq.append(o)
        if len(uniq) < 4:
            continue

        random.shuffle(uniq)
        ci = uniq.index(kw)

        questions.append(
            {
                "type": "mcq",
                "bloom_level": normalize_bloom_level(
                    "remember" if (level or "").strip().lower() == "beginner" else "understand"
                ),
                "stem": stem,
                "options": uniq[:4],
                "correct_index": int(ci),
                "explanation": f"Từ/cụm từ phù hợp nhất là '{kw}'.",
                "sources": [{"chunk_id": int(chunk_id)}],
            }
        )

    return questions
def _generate_mcq_from_chunks(topic: str, level: str, question_count: int, chunks: List[Dict[str, Any]], excluded_question_ids: List[int] | None = None) -> List[Dict[str, Any]]:
    """Quiz generator WITHOUT any hard-coded subject templates.

    Chỉ dùng nội dung trong các chunks truy xuất từ RAG:
    1) MCQ hỏi THUẬT NGỮ từ mô tả/định nghĩa (term-from-definition).
    2) MCQ dạng "X bao gồm..." (includes/bao gồm) nếu phát hiện được.
    3) MCQ hỏi mô tả/định nghĩa của thuật ngữ (definition-from-term).

    Không có ngân hàng câu hỏi sẵn theo Python hay bất kỳ môn nào khác.
    """
    if not chunks:
        raise ValueError("No chunks to generate questions")

    _ = excluded_question_ids or []
    qc = max(0, int(question_count))
    questions: List[Dict[str, Any]] = []

    # 1) Ask TERM from description (less "document-like" than quoting definitions as options)
    term_qs = _generate_term_from_definition_mcqs(topic=topic, level=level, question_count=qc, chunks=chunks)
    questions.extend(term_qs)

    # 2) Includes/bao gồm MCQs (conceptual, not excerpt-based)
    remaining = qc - len(questions)
    if remaining > 0:
        inc_qs = _generate_includes_mcqs(topic=topic, level=level, question_count=remaining, chunks=chunks)
        questions.extend(inc_qs)

    # 3) Ask definition from TERM (still grounded, but phrased pedagogically)
    remaining = qc - len(questions)
    if remaining > 0:
        def_qs = _generate_definition_mcqs(topic=topic, level=level, question_count=remaining, chunks=chunks)
        questions.extend(def_qs)

    # 4) Last-resort fallback: Cloze MCQs (fill-in-the-blank) grounded to sentences.
    # This works even when "X là Y" patterns are rare or noisy.
    remaining = qc - len(questions)
    if remaining > 0:
        term_pool = _extract_term_pool(chunks, max_terms=160)
        cloze_qs = _generate_cloze_mcqs(topic=topic, level=level, question_count=remaining, chunks=chunks, term_pool=term_pool)
        questions.extend(cloze_qs)

    return questions[:qc]
def _generate_mcq_from_chunks_legacy(topic: str, level: str, question_count: int, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Legacy generator kept as fallback."""
    chunk_snips: List[Tuple[str, int]] = [(_snippet(c["text"], 110), int(c["chunk_id"])) for c in chunks]
    option_keys = ["A", "B", "C", "D"]

    questions: List[Dict[str, Any]] = []
    for i in range(question_count):
        main_idx = i % len(chunk_snips)
        correct_text, main_chunk_id = chunk_snips[main_idx]

        distractors: List[str] = []
        for j, (snip, _) in enumerate(chunk_snips):
            if j == main_idx:
                continue
            distractors.append(snip)
            if len(distractors) >= 3:
                break
        if len(distractors) < 3:
            # Not enough distinct evidence to create clean distractors.
            continue

        correct_pos = i % 4
        options_dict: Dict[str, str] = {}
        di = 0
        for k_idx, k in enumerate(option_keys):
            if k_idx == correct_pos:
                options_dict[k] = correct_text
            else:
                options_dict[k] = distractors[di]
                di += 1

        options_list = [options_dict["A"], options_dict["B"], options_dict["C"], options_dict["D"]]
        lang = preferred_question_language(chunks)
        is_vi = (lang.get("code") == "vi")
        questions.append(
            {
                "type": "mcq",
                "stem": (
                    f"Phát biểu nào sau đây đúng nhất về '{topic}'?"
                    if is_vi
                    else f"Which statement is MOST correct about '{topic}'?"
                ),
                "options": options_list,
                "correct_index": correct_pos,
                "explanation": (
                    "Đáp án đúng phản ánh đúng kiến thức của chủ đề."
                    if is_vi
                    else "The correct option best reflects the concept."
                ),
                "sources": [{"chunk_id": main_chunk_id}],
            }
        )
    return questions


# =====================
# MCQ sanitation (cleaner filtering)
# =====================

_TOPIC_PREFIX_RX = re.compile(r"^\s*chủ\s*đề\s*[\"'“][^\"'”]+[\"'”]\s*:\s*", flags=re.IGNORECASE)


def _norm_stem_for_dedupe(stem: str) -> str:
    s = " ".join((stem or "").split()).strip().lower()
    s = _TOPIC_PREFIX_RX.sub("", s)
    # soften punctuation differences
    s = re.sub(r"[\s\"'“”‘’]+", " ", s)
    s = re.sub(r"[^a-z0-9à-ỹ ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s



def _trim_opt(s: str, max_len: int = 220) -> str:
    s2 = " ".join((s or "").split()).strip()
    if len(s2) <= max_len:
        return s2
    return s2[: max_len - 1].rstrip() + "…"


def clean_mcq_questions(questions: List[Dict[str, Any]], *, limit: int | None = None) -> List[Dict[str, Any]]:
    """Clean/filter MCQ questions to be demo-friendly *without adding any pre-made options*.

    We only:
    - remove invalid questions
    - de-duplicate stems/options
    - trim overly long options
    - enforce exactly 4 unique options with 1 correct answer
    """
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for q in (questions or []):
        if not isinstance(q, dict):
            continue

        if (q.get("type") or "").lower() != "mcq":
            out.append(q)
            continue

        stem_raw = " ".join(str(q.get("stem") or "").split()).strip()
        if len(stem_raw) < 10:
            continue

        key = _norm_stem_for_dedupe(stem_raw)
        if not key or key in seen:
            continue
        seen.add(key)

        opts_raw = q.get("options")
        if not isinstance(opts_raw, list):
            continue

        opts_trim = [_trim_opt(str(x)) for x in opts_raw if str(x).strip()]
        if len(opts_trim) < 4:
            continue

        try:
            ci = int(q.get("correct_index"))
        except Exception:
            continue
        if ci < 0 or ci >= len(opts_trim):
            continue

        correct = opts_trim[ci].strip()
        if not correct:
            continue

        # De-dup options while preserving order
        uniq: List[str] = []
        seen_opt: set[str] = set()
        for o in opts_trim:
            ol = o.lower()
            if ol in seen_opt:
                continue
            seen_opt.add(ol)
            uniq.append(o)

        if len(uniq) < 4:
            continue

        wrongs = [o for o in uniq if o.lower() != correct.lower()]
        if len(wrongs) < 3:
            continue

        options = [correct] + wrongs[:3]
        random.shuffle(options)
        ci2 = options.index(correct)

        explanation = " ".join(str(q.get("explanation") or "").split()).strip()
        hint = " ".join(str(q.get("hint") or "").split()).strip()
        related_concept = " ".join(str(q.get("related_concept") or "").split()).strip()
        sources = q.get("sources") or []
        if isinstance(sources, dict):
            sources = [sources]

        out.append(
            {
                **q,
                "stem": stem_raw,
                "options": options,
                "correct_index": int(ci2),
                "explanation": explanation,
                "hint": hint,
                "related_concept": related_concept,
                "sources": sources,
            }
        )

        if limit is not None and len(out) >= int(limit):
            break

    return out

def generate_quiz_with_rag(db: Session, payload: QuizGenerateRequest) -> Dict[str, Any]:
    ensure_user_exists(db, int(payload.user_id), role="student")

    # 1) retrieve context (also logs rag_queries)
    filters = dict(payload.rag.filters or {})
    # Auto-scope to best-matching teacher documents to avoid mixing unrelated materials.
    if not filters.get("document_ids"):
        auto_ids = auto_document_ids_for_query(db, payload.rag.query or payload.topic, preferred_user_id=settings.DEFAULT_TEACHER_ID, max_docs=2)
        if auto_ids:
            filters["document_ids"] = auto_ids

    rag_data = corrective_retrieve_and_log(
        db=db,
        query=payload.rag.query,
        top_k=payload.rag.top_k,
        filters=filters,
        topic=payload.topic,
    )
    chunks = rag_data.get("chunks") or []

    # OCR/text-quality guard: avoid generating questions from garbled OCR.
    good, bad = filter_chunks_by_quality(chunks, min_score=float(settings.OCR_MIN_QUALITY_SCORE))
    bad_ratio = float(len(bad)) / float(max(1, len(chunks)))
    if (not good) or (bad_ratio >= float(settings.OCR_BAD_CHUNK_RATIO) and len(good) < 2):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "NEED_CLEAN_TEXT",
                "message": "CONTEXT bị lỗi OCR / rời rạc nên không thể sinh câu hỏi bám tài liệu.",
                "reason": f"bad_chunk_ratio={bad_ratio:.2f}, good={len(good)}, total={len(chunks)}",
                "suggestion": "Hãy upload file .docx hoặc PDF có text layer / hoặc copy-paste đúng mục cần ra đề.",
                "debug": {"sample_bad": bad[:2]},
            },
        )
    # Prefer clean chunks for generation.
    chunks = good

    # Remove obvious practice/answer-key lines so the generator doesn't "learn" from existing quizzes/keys.
    cleaned_chunks = []
    for c in chunks:
        txt = clean_text_for_generation(str(c.get('text') or ''))
        if len(txt) >= 60:
            c2 = dict(c)
            c2['text'] = txt
            cleaned_chunks.append(c2)
    if cleaned_chunks:
        chunks = cleaned_chunks

    # If retrieval is too thin, auto-augment from the selected topic's chunk-range.
    # This makes sure *every topic* can generate quizzes at any difficulty level.
    min_need = max(6, int(payload.question_count) * 2)
    doc_ids = filters.get("document_ids") or []
    if isinstance(doc_ids, int):
        doc_ids = [doc_ids]
    if len(chunks) < min_need and doc_ids and (payload.topic or '').strip():
        key = " ".join((payload.topic or "").lower().split())
        try:
            dt = (
                db.query(DocumentTopic)
                .filter(DocumentTopic.document_id.in_([int(x) for x in doc_ids]))
                .filter(func.lower(DocumentTopic.title) == key)
                .order_by(DocumentTopic.document_id.asc())
                .first()
            )
        except Exception:
            dt = None

        if dt and dt.start_chunk_index is not None and dt.end_chunk_index is not None:
            # Expand evidence range ONLY for generation, so topic display remains clean.
            len_rows = (
                db.query(DocumentChunk.chunk_index, func.length(DocumentChunk.text))
                .filter(DocumentChunk.document_id == int(dt.document_id))
                .order_by(DocumentChunk.chunk_index.asc())
                .all()
            )
            chunk_lengths = [int(r[1] or 0) for r in len_rows]
            (s2, e2) = ensure_topic_chunk_ranges_ready_for_quiz(
                [(int(dt.start_chunk_index), int(dt.end_chunk_index))],
                chunk_lengths=chunk_lengths,
            )[0]

            rows = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == int(dt.document_id))
                .filter(DocumentChunk.chunk_index >= int(s2))
                .filter(DocumentChunk.chunk_index <= int(e2))
                .order_by(DocumentChunk.chunk_index.asc())
                .limit(220)
                .all()
            )
            extra = [
                {
                    "chunk_id": r.id,
                    "text": r.text,
                    "document_id": r.document_id,
                    "score": 1.0,
                    "title": str(r.document_id),
                }
                for r in rows
                if (r.text or '').strip()
            ]
            if extra:
                # Merge + dedupe by chunk_id
                uniq: Dict[int, Dict[str, Any]] = {}
                for c in (chunks + extra):
                    try:
                        cid = int(c.get('chunk_id'))
                    except Exception:
                        continue
                    uniq[cid] = c
                chunks = list(uniq.values())
                good2, _bad2 = filter_chunks_by_quality(chunks, min_score=float(settings.OCR_MIN_QUALITY_SCORE))
                if good2:
                    # Clean again after augmentation
                    cleaned_chunks2 = []
                    for c in good2:
                        txt = clean_text_for_generation(str(c.get('text') or ''))
                        if len(txt) >= 60:
                            c2 = dict(c)
                            c2['text'] = txt
                            cleaned_chunks2.append(c2)
                    chunks = cleaned_chunks2 or good2
    if not chunks:
        raise HTTPException(status_code=404, detail="No relevant chunks found for this query")

    # 2) generate questions
    # Prefer LLM-based generation when available (better quality, more paraphrased).
    gen_mode = (settings.QUIZ_GEN_MODE or "auto").strip().lower()
    gen_questions: List[Dict[str, Any]] = []
    if gen_mode in {"auto", "llm"}:
        try:
            gen_questions = _generate_mcq_with_llm(payload.topic, payload.level, payload.question_count, chunks)
        except HTTPException:
            raise
        except Exception:
            gen_questions = []
    if not gen_questions:
        gen_questions = _generate_mcq_from_chunks(payload.topic, payload.level, payload.question_count, chunks)

    # Final sanitation: remove duplicates / fix options so the FE always receives clean MCQs.
    gen_questions = clean_mcq_questions(gen_questions, limit=int(payload.question_count))

    # Optional LLM editor pass: refine stems/distractors/explanations while staying grounded.
    # Runs only when enabled + LLM is available. In auto mode, we only refine when we detect weak questions.
    if gen_questions and _quiz_refine_enabled(questions=gen_questions, gen_mode=gen_mode):
        try:
            gen_questions = _llm_refine_mcqs(topic=payload.topic, level=payload.level, chunks=chunks, questions=gen_questions)
            gen_questions = clean_mcq_questions(gen_questions, limit=int(payload.question_count))
        except Exception:
            # Never break quiz generation if the editor pass fails.
            gen_questions = clean_mcq_questions(gen_questions, limit=int(payload.question_count))

    
    # Ensure questions are standalone (no document references). This is a lightweight pass; max_rewrites=0 avoids extra LLM calls here.
    gen_questions = enforce_standalone_mcqs(topic=payload.topic, level=payload.level, chunks=chunks, questions=gen_questions, max_rewrites=0)
    gen_questions = clean_mcq_questions(gen_questions, limit=int(payload.question_count))

# 3) persist quiz_set + questions
    quiz_set = QuizSet(user_id=payload.user_id, topic=payload.topic, level=payload.level, source_query_id=rag_data["query_id"])
    db.add(quiz_set)
    db.commit()
    db.refresh(quiz_set)

    q_models: List[Question] = []
    for order_no, q in enumerate(gen_questions):
        q_models.append(
            Question(
                quiz_set_id=quiz_set.id,
                type=q["type"],
                bloom_level=normalize_bloom_level(q.get("bloom_level")),
                stem=q["stem"],
                options=q["options"],
                correct_index=q["correct_index"],
                explanation=q.get("explanation"),
                sources=q.get("sources") or [],
                order_no=order_no,
            )
        )
    db.add_all(q_models)
    db.commit()
    for qm in q_models:
        db.refresh(qm)

    # 4) response to FE (no correct_index)
    out_questions = [
        {
            "question_id": q.id,
            "type": q.type,
            "bloom_level": q.bloom_level,
            "stem": q.stem,
            "options": q.options,
        }
        for q in q_models
    ]
    sources_out = [
        {"chunk_id": c.get("chunk_id"), "document_id": c.get("document_id"), "score": c.get("score")}
        for c in chunks
    ]

    return {"quiz_id": quiz_set.id, "topic": quiz_set.topic, "level": quiz_set.level, "questions": out_questions, "sources": sources_out}


def grade_and_store_attempt(db: Session, quiz_id: int, payload: QuizSubmitRequest) -> Dict[str, Any]:
    quiz_set = db.query(QuizSet).filter(QuizSet.id == quiz_id).first()
    if not quiz_set:
        raise HTTPException(status_code=404, detail="Quiz not found")

    # Demo-friendly: allow any numeric user_id from the UI; auto-create if missing.
    ensure_user_exists(db, int(payload.user_id), role="student")

    questions: List[Question] = db.query(Question).filter(Question.quiz_set_id == quiz_id).order_by(Question.order_no.asc()).all()
    if not questions:
        raise HTTPException(status_code=404, detail="Quiz not found")

    answer_map = {a.question_id: a.answer for a in payload.answers}

    breakdown = []
    correct_count = 0
    for q in questions:
        chosen = answer_map.get(q.id, -1)
        is_correct = int(chosen) == int(q.correct_index)
        if is_correct:
            correct_count += 1
        breakdown.append(
            {
                "question_id": q.id,
                "bloom_level": getattr(q, "bloom_level", None),
                "is_correct": bool(is_correct),
                "chosen": int(chosen),
                "correct": int(q.correct_index),
                "explanation": q.explanation,
                "sources": q.sources or [],
            }
        )

    total = len(questions)
    score_percent = int(round((correct_count / total) * 100)) if total else 0

    attempt = Attempt(
        quiz_set_id=quiz_id,
        user_id=payload.user_id,
        score_percent=score_percent,
        answers_json=[{"question_id": a.question_id, "answer": a.answer} for a in payload.answers],
        breakdown_json=breakdown,
        duration_sec=payload.duration_sec,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    # --- Adaptive: update learner mastery (weighted rule) ---
    # Rule (demo-friendly but better than constant alpha/beta):
    # - correct +alpha(level), wrong -beta(level)
    # - clamp 0..1
    # - scale down suspiciously-fast submissions

    lvl = (quiz_set.level or "beginner").strip().lower()
    if lvl not in {"beginner", "intermediate", "advanced"}:
        lvl = "beginner"

    # tuned for stability: mastery moves slowly, but is responsive over multiple quizzes
    alpha_by_level = {"beginner": 0.05, "intermediate": 0.06, "advanced": 0.075}
    beta_by_level = {"beginner": 0.03, "intermediate": 0.035, "advanced": 0.045}

    alpha = float(alpha_by_level[lvl])
    beta = float(beta_by_level[lvl])

    wrong_count = total - correct_count
    raw_delta = (correct_count * alpha) - (wrong_count * beta)

    # Duration-based scaling (prevents "click-through" abuse in demos)
    scale = 1.0
    if payload.duration_sec is not None:
        try:
            dur = float(payload.duration_sec)
            # very fast: < 6s/question => scale down
            if dur >= 0 and dur < float(total) * 6.0:
                scale = 0.6
            # extremely slow: still count, but dampen slightly
            elif dur > float(total) * 240.0:
                scale = 0.9
        except Exception:
            scale = 1.0

    delta = raw_delta * scale

    topic_key = (quiz_set.topic or "").strip().lower()

    mastery_updated = None
    profile_level_updated = None

    if topic_key:
        profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == payload.user_id).first()
        if not profile:
            profile = LearnerProfile(user_id=payload.user_id, level=lvl, mastery_json={})
            db.add(profile)
            db.flush()

        mastery_map = dict(profile.mastery_json or {})
        current = float(mastery_map.get(topic_key, 0.0))
        new_val = max(0.0, min(1.0, current + delta))
        mastery_map[topic_key] = round(new_val, 4)
        profile.mastery_json = mastery_map

        # Optional: update overall profile level based on average mastery across known topics
        try:
            vals = [float(v) for v in mastery_map.values() if v is not None]
            avg = sum(vals) / max(1.0, float(len(vals)))
            if avg < 0.4:
                profile.level = "beginner"
            elif avg < 0.7:
                profile.level = "intermediate"
            else:
                profile.level = "advanced"
            profile_level_updated = profile.level
        except Exception:
            profile_level_updated = profile.level

        db.commit()
        mastery_updated = {
            "topic": topic_key,
            "mastery": mastery_map[topic_key],
            "delta": round(float(delta), 4),
            "raw_delta": round(float(raw_delta), 4),
            "scale": round(float(scale), 3),
            "level": lvl,
        }

    return {
        "quiz_id": quiz_id,
        "attempt_id": attempt.id,
        "score_percent": score_percent,
        "correct_count": correct_count,
        "total": total,
        "breakdown": breakdown,
        "mastery_updated": mastery_updated,
    }
