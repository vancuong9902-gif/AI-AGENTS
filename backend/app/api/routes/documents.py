from __future__ import annotations

import hashlib
from io import BytesIO
from datetime import datetime, timezone

from typing import Optional, Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, Request, UploadFile, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.schemas.quiz import QuizGenerateRequest
from app.schemas.question_bank import QuestionBankGenerateRequest
from app.api.deps import get_current_user_optional, require_teacher
from app.models.user import User
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_topic import DocumentTopic
from app.models.quiz import QuizLegacy
from app.models.quiz_set import QuizSet
from app.models.question import Question
from app.core.config import settings
from app.services.document_pipeline import extract_and_chunk_with_report
from app.services.topic_service import (
    extract_topics,
    assign_topic_chunk_ranges,
    topic_range_stats,
    ensure_topic_chunk_ranges_ready_for_quiz,
    build_topic_details,
    enrich_topic_details_with_llm,
    clean_topic_text_for_display,
    split_study_and_practice,
    is_appendix_title,
    validate_and_clean_topic_title,
    extract_exercises_from_topic,
    parse_quick_check_quiz,
    build_topic_preview_for_teacher,
)
from app.services import vector_store
from app.infra.queue import is_async_enabled, enqueue
from app.tasks.index_tasks import task_index_document, task_rebuild_vector_index
from app.services.user_service import ensure_user_exists
from app.services.quiz_service import generate_quiz_with_rag
from app.services.vietnamese_font_fix import detect_broken_vn_font, fix_vietnamese_encoding
from app.services.text_quality import quality_score
from app.services.text_repair import repair_ocr_spacing_text

router = APIRouter(tags=['documents'])

DOCUMENT_PROCESS_STATUS: dict[int, dict[str, Any]] = {}


def _set_doc_status(document_id: int, *, status: str, progress_pct: int, topic_count: int = 0) -> None:
    DOCUMENT_PROCESS_STATUS[int(document_id)] = {
        'status': str(status),
        'progress_pct': max(0, min(100, int(progress_pct))),
        'topic_count': max(0, int(topic_count)),
    }


def _is_pdf(mime_type: str | None, filename: str | None) -> bool:
    mt = str(mime_type or '').lower()
    fn = str(filename or '').lower()
    return (mt == 'application/pdf') or fn.endswith('.pdf')






def _infer_page_range_from_chunks(chunks: list[DocumentChunk], start_idx: int | None, end_idx: int | None) -> tuple[int | None, int | None]:
    if start_idx is None or end_idx is None:
        return (None, None)
    vals: list[int] = []
    for c in chunks[int(start_idx): int(end_idx) + 1]:
        meta = getattr(c, 'meta', {}) or {}
        for k in ('page', 'page_num', 'page_number'):
            v = meta.get(k)
            if isinstance(v, int):
                vals.append(int(v))
                break
    if not vals:
        return (None, None)
    return (min(vals), max(vals))



def _create_topic_quick_check_quiz(db: Session, *, user_id: int, topic_title: str, study_guide_md: str) -> int | None:
    """Create QuizSet(kind=topic_quick_check) from study guide quick-check section."""
    qs_items = parse_quick_check_quiz(study_guide_md)
    if len(qs_items) < 10:
        return None

    quiz_set = QuizSet(
        user_id=int(user_id),
        kind="topic_quick_check",
        topic=(str(topic_title or "Chủ đề")[:255]),
        level="mixed",
        source_query_id=None,
        duration_seconds=600,
    )
    db.add(quiz_set)
    db.flush()

    rows: list[Question] = []
    for i, q in enumerate(qs_items[:10], 1):
        opts = [str(x).strip() for x in (q.get("options") or []) if str(x).strip()][:4]
        if len(opts) < 2:
            continue
        while len(opts) < 4:
            opts.append("Không có đáp án phù hợp")
        rows.append(
            Question(
                quiz_set_id=quiz_set.id,
                order_no=i,
                type="mcq",
                bloom_level="understand",
                stem=str(q.get("stem") or "").strip()[:1000],
                options=opts[:4],
                correct_index=0,
                explanation=None,
                estimated_minutes=1,
                sources=[{"source": "topic_study_guide"}],
            )
        )
    if len(rows) < 10:
        db.rollback()
        return None
    db.add_all(rows)
    db.flush()
    return int(quiz_set.id)


def _topic_title_for_generation(topic: DocumentTopic) -> str:
    edited = str(getattr(topic, 'teacher_edited_title', '') or '').strip()
    return edited or str(getattr(topic, 'title', '') or '').strip()

def _dynamic_topic_target(full_text: str, estimated_pages: int | None = None) -> float:
    full_len = len(full_text or '')
    page_est = int(estimated_pages or 0)
    if page_est <= 0:
        page_est = max(1, round(full_len / 2600)) if full_len > 0 else 0
    target_by_len = round(full_len / 12000) if full_len > 0 else 12
    target_by_page = round(page_est / 2.2) if page_est > 0 else 12
    return float(max(12, min(60, max(target_by_len, target_by_page))))

def _extract_topics_doc_auto(
    full_text: str,
    chunks_texts: list[str],
    *,
    mime_type: str | None,
    filename: str | None,
    max_topics: int,
    include_details: bool = True,
) -> dict[str, Any]:
    """Topic extraction with a PDF-aware heading strategy.

    For PDFs, we often want Thea-like "study topics" instead of coarse chapter-only splits.
    This helper supports a configurable strategy via TOPIC_PDF_HEADING_LEVEL:
      - topic: always use topic/heading splitting
      - chapter: always split by chapters
      - auto: try topic/heading splitting first; if it yields too few topics, fall back to chapter
    """

    is_pdf = _is_pdf(mime_type, filename)
    pdf_mode = (getattr(settings, 'TOPIC_PDF_HEADING_LEVEL', 'auto') or 'auto').strip().lower()
    if not is_pdf:
        return extract_topics(
            full_text,
            chunks_texts=chunks_texts,
            heading_level=None,
            include_details=include_details,
            max_topics=int(max_topics),
        )

    # Explicit modes
    if pdf_mode in ('chapter', 'chapters'):
        return extract_topics(
            full_text,
            chunks_texts=chunks_texts,
            heading_level='chapter',
            include_details=include_details,
            max_topics=int(max_topics),
        )
    if pdf_mode in ('topic', 'topics', 'heading', 'headings', 'lesson', 'lessons'):
        return extract_topics(
            full_text,
            chunks_texts=chunks_texts,
            heading_level=None,
            include_details=include_details,
            max_topics=int(max_topics),
        )

    # auto: evaluate both strategies and pick the more "learnable" one.
    obj_topic = extract_topics(
        full_text,
        chunks_texts=chunks_texts,
        heading_level=None,
        include_details=include_details,
        max_topics=int(max_topics),
    )
    obj_chapter = extract_topics(
        full_text,
        chunks_texts=chunks_texts,
        heading_level='chapter',
        include_details=include_details,
        max_topics=int(max_topics),
    )

    def _score(obj: dict[str, Any]) -> float:
        if str(obj.get('status') or '').upper() != 'OK':
            return -1e9
        topics = obj.get('topics') or []
        if not isinstance(topics, list) or not topics:
            return -1e9
        lens = [max(1, int(t.get('body_len') or t.get('content_len') or 1)) for t in topics]
        n = len(lens)
        avg = sum(lens) / max(1, n)
        small = sum(1 for x in lens if x < int(getattr(settings, 'TOPIC_MIN_BODY_CHARS', 1800) or 1800)) / max(1, n)
        # Penalize topic splits that look like outline-fragments (e.g., titles start with 1.1 / 2.3.1)
        # because they often become too granular and not learnable like Thea.
        import re as _re
        bad_title = 0
        chap_title = 0
        for t in topics:
            tt = str(t.get('title') or '')
            if _re.match(r"^\s*\d{1,2}(?:\.\d{1,3}){1,4}\b", tt):
                bad_title += 1
            if 'chương' in tt.lower() or 'chapter' in tt.lower():
                chap_title += 1
        bad_title_ratio = bad_title / max(1, n)
        chap_ratio = chap_title / max(1, n)

        full_len = len(full_text or '')
        page_est = max(1, round(full_len / 2600)) if full_len > 0 else 0
        target = _dynamic_topic_target(full_text, estimated_pages=page_est)

        n_penalty = abs(n - target) / max(12.0, target)
        long_doc = full_len >= 180_000 or page_est >= 70
        too_many_threshold = 45 if long_doc else 28
        too_many = 1.0 if n > too_many_threshold else 0.0
        return (avg / 2200.0) - (2.2 * small) - (1.05 * n_penalty) - (1.55 * bad_title_ratio) - (0.6 * too_many) + (0.22 * chap_ratio)

    s_topic = _score(obj_topic)
    s_chap = _score(obj_chapter)

    # Prefer chapter strategy when topic split is too granular (many small sections).
    if s_chap >= s_topic:
        return obj_chapter
    return obj_topic


@router.get('/documents')
def list_documents(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = 1,
    user: Optional[User] = Depends(get_current_user_optional),
):
    """List uploaded documents.

    Demo behavior:
    - Teacher: lists their own documents (based on X-User-Id).
    - Student/anonymous: lists documents of teacher_id=1 (default user_id).

    This keeps the demo usable even when students don't have document ownership.
    """

    if user and str(getattr(user, "role", "")).lower() == "teacher":
        user_id = int(getattr(user, "id"))
    # chunk_count per document
    counts = dict(
        db.query(DocumentChunk.document_id, func.count(DocumentChunk.id))
        .group_by(DocumentChunk.document_id)
        .all()
    )

    docs = (
        db.query(Document)
        .filter(Document.user_id == user_id)
        .order_by(Document.created_at.desc())
        .all()
    )

    # Fetch auto-extracted topic titles for quick UI display (avoid showing full bodies).
    doc_ids = [d.id for d in docs]
    topics_by_doc: dict[int, list[str]] = {}
    topics_display_by_doc: dict[int, list[str]] = {}
    if doc_ids:
        rows = (
            db.query(DocumentTopic.document_id, DocumentTopic.topic_index, DocumentTopic.title)
            .filter(DocumentTopic.document_id.in_(doc_ids))
            .order_by(DocumentTopic.document_id.asc(), DocumentTopic.topic_index.asc())
            .all()
        )
        for did, t_idx, title in rows:
            # Optionally hide appendix sections from UI listings.
            if bool(getattr(settings, 'TOPIC_HIDE_APPENDIX', True)) and is_appendix_title(str(title)):
                continue
            topics_by_doc.setdefault(int(did), []).append(str(title))
            # Do NOT add numbering in the title itself. Keep ordering via topic_index.
            topics_display_by_doc.setdefault(int(did), []).append(str(title))

    out = []
    for d in docs:
        out.append(
            {
                'document_id': d.id,
                'title': d.title,
                'filename': d.filename,
                'mime_type': d.mime_type,
                'tags': d.tags or [],
                'auto_topics': topics_by_doc.get(int(d.id), []),
                'auto_topics_display': topics_display_by_doc.get(int(d.id), topics_by_doc.get(int(d.id), [])),
                'created_at': d.created_at.isoformat() if getattr(d, 'created_at', None) else None,
                'chunk_count': int(counts.get(d.id, 0)),
            }
        )

    return {'request_id': request.state.request_id, 'data': {'documents': out}, 'error': None}


@router.get('/documents/{document_id}/chunks')
def list_document_chunks(request: Request, document_id: int, db: Session = Depends(get_db)):
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )
    out = [{'chunk_id': c.id, 'chunk_index': c.chunk_index, 'text': c.text, 'meta': c.meta} for c in chunks]
    return {'request_id': request.state.request_id, 'data': {'document_id': document_id, 'chunks': out}, 'error': None}


@router.get('/documents/{document_id}/topics')
def list_document_topics(
    request: Request,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
    detail: int = 0,
    filter: str | None = None,
    status: str | None = None,
):
    user_role = str(getattr(current_user, 'role', '') or '').strip().lower()
    is_teacher = user_role == 'teacher'

    topics_q = db.query(DocumentTopic).filter(DocumentTopic.document_id == document_id)
    if not is_teacher:
        topics_q = topics_q.filter(DocumentTopic.is_confirmed.is_(True), DocumentTopic.is_active.is_(True))
    if (filter or '').strip().lower() == 'needs_review':
        topics_q = topics_q.filter(DocumentTopic.needs_review.is_(True))
    status_norm = (status or '').strip().lower()
    if status_norm in {'pending_review', 'approved', 'rejected', 'edited'}:
        topics_q = topics_q.filter(DocumentTopic.status == status_norm)
    topics = topics_q.order_by(func.coalesce(DocumentTopic.page_start, 10**9).asc(), DocumentTopic.topic_index.asc()).all()

    # Preload chunk lengths for fast "quiz_ready" stats (no extra heavy per-topic queries).
    chunk_rows = (
        db.query(DocumentChunk.chunk_index, func.length(DocumentChunk.text))
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )
    chunk_lengths = [int(r[1] or 0) for r in chunk_rows]

    out = []
    llm_view_used = 0
    llm_view_max = int(getattr(settings, 'TOPIC_LLM_VIEW_MAX_TOPICS', 8) or 8)
    # detail=1 will include a richer "topic profile" generated from the topic's chunk range.
    # This is computed on-the-fly (no DB migration needed).
    for t in topics:
        if bool(getattr(settings, 'TOPIC_HIDE_APPENDIX', True)) and is_appendix_title(str(getattr(t, 'title', '') or '')):
            continue
        item = {
            "topic_id": t.id,
            "topic_index": t.topic_index,
            "title": t.title,
            "effective_title": _topic_title_for_generation(t),
            # Frontend can show ordering using topic_index; keep titles clean.
            "display_title": t.display_title or t.title,
            "status": getattr(t, 'status', 'pending_review'),
            "teacher_edited_title": getattr(t, 'teacher_edited_title', None),
            "teacher_note": getattr(t, 'teacher_note', None),
            "reviewed_at": (t.reviewed_at.isoformat() if getattr(t, 'reviewed_at', None) else None),
            "needs_review": bool(t.needs_review),
            "extraction_confidence": float(t.extraction_confidence or 0.0),
            "page_range": [t.page_start, t.page_end],
            "summary": t.summary,
            "keywords": t.keywords or [],
            "start_chunk_index": t.start_chunk_index,
            "end_chunk_index": t.end_chunk_index,
            "has_original_exercises": bool((t.metadata_json or {}).get("has_original_exercises")),
            "original_exercise_count": len((t.metadata_json or {}).get("original_exercises") or []),
            "coverage_score": float((t.metadata_json or {}).get("coverage_score") or 0.0),
            "confidence": str((t.metadata_json or {}).get("confidence") or "low"),
            "sample_content": str((t.metadata_json or {}).get("sample_content") or ""),
            "subtopics": (t.metadata_json or {}).get("subtopics") or [],
            "page_ranges": (t.metadata_json or {}).get("page_ranges") or [],
            "quick_check_quiz_id": t.quick_check_quiz_id,
        }

        st_tight = topic_range_stats(
            start_chunk_index=t.start_chunk_index,
            end_chunk_index=t.end_chunk_index,
            chunk_lengths=chunk_lengths,
        )

        # UI should reflect REAL quiz feasibility.
        # Quiz generation expands the evidence range on-the-fly; do the same here for "quiz_ready".
        s2, e2 = (t.start_chunk_index, t.end_chunk_index)
        if t.start_chunk_index is not None and t.end_chunk_index is not None:
            try:
                (s2, e2) = ensure_topic_chunk_ranges_ready_for_quiz(
                    [(int(t.start_chunk_index), int(t.end_chunk_index))],
                    chunk_lengths=chunk_lengths,
                )[0]
            except Exception:
                s2, e2 = (t.start_chunk_index, t.end_chunk_index)

        st = topic_range_stats(
            start_chunk_index=s2,
            end_chunk_index=e2,
            chunk_lengths=chunk_lengths,
        )
        quiz_ready = (
            st.get('chunk_span', 0) >= int(getattr(settings, 'TOPIC_MIN_CHUNKS_FOR_QUIZ', 4) or 4)
            and st.get('char_len', 0) >= int(getattr(settings, 'TOPIC_MIN_CHARS_FOR_QUIZ', 1400) or 1400)
        )

        if is_teacher:
            item["is_confirmed"] = bool(getattr(t, 'is_confirmed', False))
            item["is_active"] = bool(getattr(t, 'is_active', True))

        item["chunk_span"] = st_tight.get('chunk_span', 0)
        item["range_char_len"] = st_tight.get('char_len', 0)
        item["evidence_chunk_span"] = st.get('chunk_span', 0)
        item["evidence_char_len"] = st.get('char_len', 0)
        item["quiz_ready"] = bool(quiz_ready)

        if int(detail) == 1 and t.start_chunk_index is not None and t.end_chunk_index is not None:
            chs = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == document_id)
                .filter(DocumentChunk.chunk_index >= int(t.start_chunk_index))
                .filter(DocumentChunk.chunk_index <= int(t.end_chunk_index))
                .order_by(DocumentChunk.chunk_index.asc())
                .all()
            )
            body_raw = "\n\n".join([c.text or "" for c in chs]).strip()
            body_view = clean_topic_text_for_display(body_raw)
            study_view, practice_view = split_study_and_practice(body_view)
            study_view = study_view or body_view

            item.update(build_topic_details(study_view, title=t.title))

            # Optional: generate a Thea-like study guide on-the-fly for richer "tài liệu" view.
            # Limited to first N topics to avoid heavy load.
            if llm_view_used < llm_view_max:
                try:
                    llm_det = enrich_topic_details_with_llm(study_view, title=t.title)
                    if isinstance(llm_det, dict) and llm_det:
                        # Only override when present; keep deterministic parts as fallback.
                        if llm_det.get('summary'):
                            item['summary'] = str(llm_det.get('summary')).strip()[:420]
                        for k in ('outline', 'key_points', 'definitions', 'examples', 'formulas', 'study_guide_md', 'self_check'):
                            if llm_det.get(k):
                                item[k] = llm_det.get(k)
                        llm_view_used += 1
                except Exception:
                    pass
            item["content_preview"] = " ".join(study_view.split())[:1600]
            item["content_len"] = len(" ".join(study_view.split()))
            item["has_more_content"] = item["content_len"] > 1600

            if practice_view:
                pv = " ".join(practice_view.split())
                item["practice_preview"] = pv[:900]
                item["practice_len"] = len(pv)
                item["has_more_practice"] = len(pv) > 900
        out.append(item)
    needs_review_count = sum(1 for x in out if bool(x.get('needs_review')))

    doc = db.query(Document).filter(Document.id == document_id).first()
    raw_doc_text = str(getattr(doc, 'content', '') or '')
    had_font_issues = bool(detect_broken_vn_font(raw_doc_text)) if raw_doc_text else False
    repaired_text = repair_ocr_spacing_text(fix_vietnamese_encoding(raw_doc_text)) if raw_doc_text else ''
    font_quality_score = float(quality_score(repaired_text if repaired_text else raw_doc_text)) if (raw_doc_text or repaired_text) else 0.0
    repair_applied = bool(raw_doc_text and repaired_text and repaired_text != raw_doc_text)

    return {
        'request_id': request.state.request_id,
        'data': {
            'document_id': document_id,
            'topics': out,
            'needs_review_count': needs_review_count,
            'font_quality_score': round(font_quality_score, 4),
            'had_font_issues': had_font_issues,
            'repair_applied': repair_applied,
        },
        'error': None,
    }




@router.post('/documents/{document_id}/topics/regenerate')
def regenerate_document_topics(
    request: Request,
    document_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    """Re-run topic extraction for an existing document.

    Useful after updating the topic extraction logic.
    """

    doc = db.query(Document).filter(Document.id == int(document_id)).first()
    if not doc:
        raise HTTPException(status_code=404, detail='Document not found')

    # Only allow the owning teacher to regenerate topics
    if int(getattr(doc, 'user_id', 0) or 0) != int(getattr(teacher, 'id')):
        raise HTTPException(status_code=403, detail='Not allowed')

    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == int(document_id))
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )
    full_text = str(getattr(doc, 'content', '') or '')

    topic_obj = _extract_topics_doc_auto(
        full_text,
        [c.text or '' for c in chunks],
        mime_type=str(getattr(doc, 'mime_type', '') or ''),
        filename=str(getattr(doc, 'filename', '') or ''),
        include_details=True,
        max_topics=int(getattr(settings, 'TOPIC_MAX_TOPICS', 60) or 60),
    )
    status = str(topic_obj.get('status') or 'SKIPPED')

    # Remove old topics
    db.query(DocumentTopic).filter(DocumentTopic.document_id == int(document_id)).delete(synchronize_session=False)
    db.commit()

    topics_payload: list[dict[str, Any]] = []
    if status == 'OK':
        topics = topic_obj.get('topics') or []
        ranges = []
        if topics and topics[0].get('start_chunk_index') is not None and topics[0].get('end_chunk_index') is not None:
            for t in topics:
                ranges.append((t.get('start_chunk_index'), t.get('end_chunk_index')))
        else:
            ranges = assign_topic_chunk_ranges(topics, chunk_lengths=[len(c.text or '') for c in chunks])

        # IMPORTANT: Keep stored ranges TIGHT for clean topic display.
        # When generating quizzes, we can expand the evidence window on-the-fly.

        topic_models: list[DocumentTopic] = []
        for i, (t, (s_idx, e_idx)) in enumerate(zip(topics, ranges)):
            cleaned_title, title_warnings = validate_and_clean_topic_title(str(t.get('title') or '').strip()[:255])
            page_start, page_end = _infer_page_range_from_chunks(chunks, s_idx, e_idx)
            original_exercises = extract_exercises_from_topic(
                str(t.get('content_preview') or t.get('summary') or ''),
                str(t.get('title') or ''),
            )
            topic_body = ""
            if s_idx is not None and e_idx is not None:
                try:
                    topic_body = "\n\n".join([(c.text or "") for c in chunks[int(s_idx): int(e_idx) + 1]]).strip()
                except Exception:
                    topic_body = ""
            quick_check_quiz_id = None
            try:
                det = build_topic_details(topic_body, title=str(t.get('title') or ''))
                sg = str(det.get('study_guide_md') or '').strip()
                if sg:
                    quick_check_quiz_id = _create_topic_quick_check_quiz(
                        db,
                        user_id=int(getattr(doc, 'user_id', 0) or 0),
                        topic_title=str(t.get('title') or ''),
                        study_guide_md=sg,
                    )
            except Exception:
                quick_check_quiz_id = None
            tm = DocumentTopic(
                document_id=int(document_id),
                is_confirmed=False,
                topic_index=i,
                title=(cleaned_title or str(t.get('title') or '').strip())[:255],
                display_title=(cleaned_title or str(t.get('title') or '').strip())[:255],
                needs_review=bool(t.get('needs_review') or title_warnings),
                extraction_confidence=float(t.get('extraction_confidence') or 0.0),
                summary=str(t.get('summary') or '').strip(),
                keywords=[str(x).strip() for x in (t.get('keywords') or []) if str(x).strip()],
                start_chunk_index=s_idx,
                end_chunk_index=e_idx,
                page_start=page_start,
                page_end=page_end,
                quick_check_quiz_id=quick_check_quiz_id,
                metadata_json={
                    "original_exercises": (t.get("original_exercises") or []),
                    "has_original_exercises": bool(t.get("has_original_exercises")),
                    "coverage_score": float(t.get("coverage_score") or 0.0),
                    "confidence": str(t.get("confidence") or "low"),
                    "sample_content": str(t.get("sample_content") or ""),
                    "subtopics": (t.get("subtopics") or []),
                    "page_ranges": (t.get("page_ranges") or []),
                },
            )
            topic_models.append(tm)

        if topic_models:
            db.add_all(topic_models)
            db.commit()
            for tm, t in zip(topic_models, topics):
                chunk_lengths = [len(c.text or '') for c in chunks]
                stats_tight = topic_range_stats(
                    start_chunk_index=tm.start_chunk_index,
                    end_chunk_index=tm.end_chunk_index,
                    chunk_lengths=chunk_lengths,
                )
                s2, e2 = (tm.start_chunk_index, tm.end_chunk_index)
                if tm.start_chunk_index is not None and tm.end_chunk_index is not None:
                    try:
                        (s2, e2) = ensure_topic_chunk_ranges_ready_for_quiz(
                            [(int(tm.start_chunk_index), int(tm.end_chunk_index))],
                            chunk_lengths=chunk_lengths,
                        )[0]
                    except Exception:
                        s2, e2 = (tm.start_chunk_index, tm.end_chunk_index)
                stats = topic_range_stats(
                    start_chunk_index=s2,
                    end_chunk_index=e2,
                    chunk_lengths=chunk_lengths,
                )
                quiz_ready = (
                    stats.get('chunk_span', 0) >= int(getattr(settings, 'TOPIC_MIN_CHUNKS_FOR_QUIZ', 4) or 4)
                    and stats.get('char_len', 0) >= int(getattr(settings, 'TOPIC_MIN_CHARS_FOR_QUIZ', 1400) or 1400)
                )
                topics_payload.append(
                    {
                        'topic_id': tm.id,
                        'topic_index': tm.topic_index,
                        'title': tm.title,
                        'effective_title': _topic_title_for_generation(tm),
                        'display_title': tm.display_title or tm.title,
                        'status': tm.status,
                        'teacher_edited_title': tm.teacher_edited_title,
                        'teacher_note': tm.teacher_note,
                        'reviewed_at': tm.reviewed_at.isoformat() if tm.reviewed_at else None,
                        'is_confirmed': bool(getattr(tm, 'is_confirmed', False)),
                        'needs_review': bool(tm.needs_review),
                        'extraction_confidence': float(tm.extraction_confidence or 0.0),
                        'page_range': [tm.page_start, tm.page_end],
                        'summary': tm.summary,
                        'keywords': tm.keywords or [],
                        'has_original_exercises': bool((tm.metadata_json or {}).get('has_original_exercises')),
                        'original_exercise_count': len((tm.metadata_json or {}).get('original_exercises') or []),
                        'coverage_score': float((tm.metadata_json or {}).get('coverage_score') or 0.0),
                        'confidence': str((tm.metadata_json or {}).get('confidence') or 'low'),
                        'sample_content': str((tm.metadata_json or {}).get('sample_content') or ''),
                        'subtopics': (tm.metadata_json or {}).get('subtopics') or [],
                        'page_ranges': (tm.metadata_json or {}).get('page_ranges') or [],
                        'quick_check_quiz_id': tm.quick_check_quiz_id,
                        'start_chunk_index': tm.start_chunk_index,
                        'end_chunk_index': tm.end_chunk_index,
                        'chunk_span': stats_tight.get('chunk_span', 0),
                        'range_char_len': stats_tight.get('char_len', 0),
                        'evidence_chunk_span': stats.get('chunk_span', 0),
                        'evidence_char_len': stats.get('char_len', 0),
                        'quiz_ready': bool(quiz_ready),
                        'outline': (t.get('outline') or []),
                        'key_points': (t.get('key_points') or []),
                        'definitions': (t.get('definitions') or []),
                        'examples': (t.get('examples') or []),
                        'formulas': (t.get('formulas') or []),
                        'sources': (t.get('sources') or []),
                        'external_notes': (t.get('external_notes') or []),
                        'content_preview': t.get('content_preview'),
                        'content_len': t.get('content_len'),
                        'has_more_content': t.get('has_more_content'),
                    }
                )

    return {
        'request_id': request.state.request_id,
        'data': {
            'document_id': int(document_id),
            'topics_status': status,
            'topics_reason': topic_obj.get('reason'),
            'quality': topic_obj.get('quality'),
            'topics': topics_payload,
        },
        'error': None,
    }


@router.get('/documents/{document_id}/topics/preview')
@router.get('/v1/documents/{document_id}/topics/preview')
def preview_document_topics(
    request: Request,
    document_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    doc = db.query(Document).filter(Document.id == int(document_id)).first()
    if not doc:
        raise HTTPException(status_code=404, detail='Document not found')
    if int(doc.user_id) != int(getattr(teacher, 'id')):
        raise HTTPException(status_code=403, detail='Not allowed')

    try:
        payload = build_topic_preview_for_teacher(int(document_id), db)
    except ValueError:
        raise HTTPException(status_code=404, detail='Document not found')

    return {
        'request_id': request.state.request_id,
        'data': payload,
        'error': None,
    }


@router.get('/documents/{document_id}/topics/{topic_id}')
def get_document_topic_detail(
    request: Request,
    document_id: int,
    topic_id: int,
    db: Session = Depends(get_db),
    include_content: int = 1,
):
    t = (
        db.query(DocumentTopic)
        .filter(DocumentTopic.document_id == document_id)
        .filter(DocumentTopic.id == topic_id)
        .first()
    )
    if not t:
        raise HTTPException(status_code=404, detail='Topic not found')

    # Hide appendix topics from the public UI unless explicitly enabled.
    if bool(getattr(settings, 'TOPIC_HIDE_APPENDIX', True)) and is_appendix_title(str(getattr(t, 'title', '') or '')):
        raise HTTPException(status_code=404, detail='Topic not found')

    item = {
        "topic_id": t.id,
        "topic_index": t.topic_index,
        "title": t.title,
        "effective_title": _topic_title_for_generation(t),
        "display_title": t.display_title or t.title,
        "status": getattr(t, 'status', 'pending_review'),
        "teacher_edited_title": getattr(t, 'teacher_edited_title', None),
        "teacher_note": getattr(t, 'teacher_note', None),
        "reviewed_at": (t.reviewed_at.isoformat() if getattr(t, 'reviewed_at', None) else None),
        "needs_review": bool(t.needs_review),
        "extraction_confidence": float(t.extraction_confidence or 0.0),
        "page_range": [t.page_start, t.page_end],
        "summary": t.summary,
        "keywords": t.keywords or [],
        "start_chunk_index": t.start_chunk_index,
        "end_chunk_index": t.end_chunk_index,
        "has_original_exercises": bool((t.metadata_json or {}).get("has_original_exercises")),
        "original_exercise_count": len((t.metadata_json or {}).get("original_exercises") or []),
    }

    body = ''
    included_chunk_ids: list[int] = []
    if t.start_chunk_index is not None and t.end_chunk_index is not None:
        chs = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .filter(DocumentChunk.chunk_index >= int(t.start_chunk_index))
            .filter(DocumentChunk.chunk_index <= int(t.end_chunk_index))
            .order_by(DocumentChunk.chunk_index.asc())
            .all()
        )
        body = "\n\n".join([c.text or '' for c in chs]).strip()
        included_chunk_ids = [c.id for c in chs]
        item["included_chunk_ids"] = included_chunk_ids

    body_view = clean_topic_text_for_display(body)

    study_view, practice_view = split_study_and_practice(body_view)
    study_view = study_view or body_view

    item.update(build_topic_details(study_view, title=t.title))
    item["content_preview"] = " ".join(study_view.split())[:1600]
    item["content_len"] = len(" ".join(study_view.split()))
    item["has_more_content"] = item["content_len"] > 1600
    if practice_view:
        pv = " ".join(practice_view.split())
        item["practice_preview"] = pv[:900]
        item["practice_len"] = len(pv)
        item["has_more_practice"] = len(pv) > 900
    if int(include_content) == 1:
        item["content"] = study_view
        if practice_view:
            item["practice"] = practice_view

    return {"request_id": request.state.request_id, "data": item, "error": None}


@router.patch('/documents/{document_id}/topics/{topic_id}')
def review_document_topic(
    request: Request,
    document_id: int,
    topic_id: int,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    doc = db.query(Document).filter(Document.id == int(document_id)).first()
    if not doc:
        raise HTTPException(status_code=404, detail='Document not found')
    if int(doc.user_id) != int(getattr(teacher, 'id')):
        raise HTTPException(status_code=403, detail='Not allowed')

    topic = (
        db.query(DocumentTopic)
        .filter(DocumentTopic.document_id == int(document_id))
        .filter(DocumentTopic.id == int(topic_id))
        .first()
    )
    if not topic:
        raise HTTPException(status_code=404, detail='Topic not found')

    status = payload.get('status')
    if status is not None:
        status = str(status).strip().lower()
        if status not in {'pending_review', 'approved', 'rejected', 'edited'}:
            raise HTTPException(status_code=422, detail='Invalid status')
        topic.status = status

    if 'title' in payload:
        new_title = str(payload.get('title') or '').strip()
        if not new_title:
            topic.teacher_edited_title = None
        else:
            cleaned, _warnings = validate_and_clean_topic_title(new_title)
            topic.teacher_edited_title = (cleaned or new_title)[:255]
            if topic.status in {'pending_review', 'approved'}:
                topic.status = 'edited'

    if 'note' in payload or 'teacher_note' in payload:
        note = payload.get('note') if 'note' in payload else payload.get('teacher_note')
        note_value = str(note or '').strip()
        topic.teacher_note = note_value or None

    if any(k in payload for k in ('status', 'title', 'note', 'teacher_note')):
        topic.reviewed_at = datetime.now(timezone.utc)

    db.add(topic)
    db.commit()
    db.refresh(topic)

    return {
        'request_id': request.state.request_id,
        'data': {
            'topic_id': int(topic.id),
            'document_id': int(document_id),
            'title': topic.title,
            'effective_title': _topic_title_for_generation(topic),
            'display_title': topic.display_title,
            'status': topic.status,
            'teacher_edited_title': topic.teacher_edited_title,
            'teacher_note': topic.teacher_note,
            'reviewed_at': topic.reviewed_at.isoformat() if topic.reviewed_at else None,
            'is_confirmed': bool(getattr(topic, 'is_confirmed', False)),
        },
        'error': None,
    }


@router.post('/documents/{doc_id}/confirm-topics')
def confirm_document_topics(
    request: Request,
    doc_id: int,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    doc = db.query(Document).filter(Document.id == int(doc_id)).first()
    if not doc:
        raise HTTPException(status_code=404, detail='Document not found')
    if int(doc.user_id) != int(getattr(teacher, 'id')):
        raise HTTPException(status_code=403, detail='Not allowed')

    raw_topics = payload.get('topics') if isinstance(payload, dict) else None
    if not isinstance(raw_topics, list) or not raw_topics:
        raise HTTPException(status_code=422, detail='topics is required')

    # Support both payload styles:
    # 1) [{id, name, confirmed}] (legacy)
    # 2) ["topic A", "topic B"] (simple confirm flow)
    if raw_topics and all(not isinstance(item, dict) for item in raw_topics):
        titles = [str(t).strip() for t in raw_topics if str(t).strip()]
        if not titles:
            raise HTTPException(status_code=422, detail='Cần ít nhất 1 topic')

        db.query(DocumentTopic).filter(DocumentTopic.document_id == int(doc_id)).delete()
        now = datetime.now(timezone.utc)
        for order, title in enumerate(titles):
            cleaned, _warnings = validate_and_clean_topic_title(title)
            row = DocumentTopic(
                document_id=int(doc_id),
                title=(cleaned or title)[:255],
                topic_index=int(order),
                status='approved',
                is_confirmed=True,
                confirmed_by_teacher=True,
                reviewed_at=now,
            )
            db.add(row)
        db.commit()
        return {
            'request_id': request.state.request_id,
            'data': {
                'document_id': int(doc_id),
                'topics_confirmed': len(titles),
                'topics': titles,
            },
            'error': None,
        }

    db_topics = {
        int(t.id): t
        for t in db.query(DocumentTopic).filter(DocumentTopic.document_id == int(doc_id)).all()
    }
    if not db_topics:
        raise HTTPException(status_code=400, detail='No topics found for document')

    now = datetime.now(timezone.utc)
    ordered_confirmed_ids: list[int] = []
    touched_ids: set[int] = set()

    for item in raw_topics:
        if not isinstance(item, dict):
            continue
        try:
            topic_id = int(item.get('id'))
        except Exception:
            continue
        topic = db_topics.get(topic_id)
        if not topic:
            continue

        touched_ids.add(topic_id)
        confirmed = bool(item.get('confirmed', True))
        topic.is_confirmed = confirmed
        topic.confirmed_by_teacher = confirmed

        if 'name' in item:
            new_title = str(item.get('name') or '').strip()
            if new_title:
                cleaned, _warnings = validate_and_clean_topic_title(new_title)
                topic.teacher_edited_title = (cleaned or new_title)[:255]

        if confirmed:
            topic.status = 'approved'
            ordered_confirmed_ids.append(topic_id)
        topic.reviewed_at = now
        db.add(topic)

    for topic_id, topic in db_topics.items():
        if topic_id not in touched_ids:
            topic.is_confirmed = False
            topic.confirmed_by_teacher = False
            db.add(topic)

    for order, topic_id in enumerate(ordered_confirmed_ids):
        topic = db_topics.get(topic_id)
        if topic:
            topic.topic_index = int(order)
            db.add(topic)

    db.commit()

    return {
        'request_id': request.state.request_id,
        'data': {
            'document_id': int(doc_id),
            'confirmed_count': len(ordered_confirmed_ids),
            'topics': [
                {
                    'id': int(t.id),
                    'name': _topic_title_for_generation(t),
                    'confirmed': bool(getattr(t, 'is_confirmed', False)),
                }
                for t in sorted(db_topics.values(), key=lambda x: (int(getattr(x, 'topic_index', 0)), int(x.id)))
            ],
            'entry_test_generation': {
                'triggered': len(ordered_confirmed_ids) > 0,
                'status': 'ready_after_teacher_confirmation' if ordered_confirmed_ids else 'skipped_no_confirmed_topics',
            },
        },
        'error': None,
    }



@router.patch('/documents/{document_id}/topics/confirm')
def publish_document_topics(
    request: Request,
    document_id: int,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    doc = db.query(Document).filter(Document.id == int(document_id)).first()
    if not doc:
        raise HTTPException(status_code=404, detail='Document not found')
    if int(doc.user_id) != int(getattr(teacher, 'id')):
        raise HTTPException(status_code=403, detail='Not allowed')

    topic_items = payload.get('topics') or []
    if not isinstance(topic_items, list) or not topic_items:
        raise HTTPException(status_code=400, detail='topics is required')

    topics = db.query(DocumentTopic).filter(DocumentTopic.document_id == int(document_id)).all()
    topic_by_id = {int(t.id): t for t in topics}
    now = datetime.now(timezone.utc)

    updated = []
    for item in topic_items:
        if not isinstance(item, dict):
            continue
        topic_id = item.get('topic_id')
        try:
            topic_id = int(topic_id)
        except Exception:
            continue

        topic = topic_by_id.get(topic_id)
        if not topic:
            continue

        include = bool(item.get('include', True))
        topic.is_confirmed = True
        topic.is_active = include

        if 'title' in item:
            raw_title = str(item.get('title') or '').strip()
            if raw_title:
                cleaned, _warnings = validate_and_clean_topic_title(raw_title)
                topic.title = (cleaned or raw_title)[:255]

        topic.updated_at = now
        db.add(topic)
        updated.append(topic)

    if not updated:
        raise HTTPException(status_code=400, detail='No valid topics to publish')

    db.commit()

    return {
        'request_id': request.state.request_id,
        'data': {
            'document_id': int(document_id),
            'topics': [
                {
                    'topic_id': int(t.id),
                    'title': t.title,
                    'is_confirmed': bool(getattr(t, 'is_confirmed', False)),
                    'is_active': bool(getattr(t, 'is_active', True)),
                }
                for t in sorted(updated, key=lambda x: (int(getattr(x, 'topic_index', 0)), int(x.id)))
            ],
        },
        'error': None,
    }


@router.post('/documents/{doc_id}/topics/confirm')
@router.post('/v1/documents/{doc_id}/topics/confirm')
def confirm_document_topics_v2(
    request: Request,
    doc_id: int,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    doc = db.query(Document).filter(Document.id == int(doc_id)).first()
    if not doc:
        raise HTTPException(status_code=404, detail='Document not found')
    if int(doc.user_id) != int(getattr(teacher, 'id')):
        raise HTTPException(status_code=403, detail='Not allowed')

    approved_ids = {int(x) for x in (payload.get('approved_topic_ids') or [])}
    rejected_ids = {int(x) for x in (payload.get('rejected_topic_ids') or [])}
    renamed_topics = payload.get('renamed_topics') or {}
    if not isinstance(renamed_topics, dict):
        renamed_topics = {}

    topics = db.query(DocumentTopic).filter(DocumentTopic.document_id == int(doc_id)).all()
    topic_by_id = {int(t.id): t for t in topics}
    if not topic_by_id:
        raise HTTPException(status_code=400, detail='No topics found for document')

    now = datetime.now(timezone.utc)
    approved_count = 0
    rejected_count = 0
    for topic_id, topic in topic_by_id.items():
        if topic_id in approved_ids:
            topic.status = 'approved'
            topic.is_confirmed = True
            approved_count += 1
        elif topic_id in rejected_ids:
            topic.status = 'rejected'
            topic.is_confirmed = False
            rejected_count += 1

        if str(topic_id) in renamed_topics:
            raw_title = str(renamed_topics.get(str(topic_id)) or '').strip()
            if raw_title:
                cleaned, _warnings = validate_and_clean_topic_title(raw_title)
                new_title = (cleaned or raw_title)[:255]
                topic.title = new_title
                topic.teacher_edited_title = new_title

        topic.reviewed_at = now
        db.add(topic)

    db.commit()

    return {
        'request_id': request.state.request_id,
        'data': {
            'approved': int(approved_count),
            'rejected': int(rejected_count),
            'message': 'Đã xác nhận topic thành công',
        },
        'error': None,
    }


@router.post('/documents/{doc_id}/topics/add-custom')
@router.post('/v1/documents/{doc_id}/topics/add-custom')
def add_custom_topic(
    request: Request,
    doc_id: int,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    doc = db.query(Document).filter(Document.id == int(doc_id)).first()
    if not doc:
        raise HTTPException(status_code=404, detail='Document not found')
    if int(doc.user_id) != int(getattr(teacher, 'id')):
        raise HTTPException(status_code=403, detail='Not allowed')

    title = str(payload.get('title') or '').strip()
    description = str(payload.get('description') or '').strip()
    if not title:
        raise HTTPException(status_code=422, detail='title is required')

    cleaned_title, _warnings = validate_and_clean_topic_title(title)
    next_index = (db.query(func.max(DocumentTopic.topic_index)).filter(DocumentTopic.document_id == int(doc_id)).scalar() or -1) + 1
    topic = DocumentTopic(
        document_id=int(doc_id),
        topic_index=int(next_index),
        title=(cleaned_title or title)[:255],
        display_title=(cleaned_title or title)[:255],
        summary=description,
        keywords=[],
        status='approved',
        is_confirmed=True,
        extraction_confidence=1.0,
        needs_review=False,
        metadata_json={'source': 'manual'},
        reviewed_at=datetime.now(timezone.utc),
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)

    return {
        'request_id': request.state.request_id,
        'data': {
            'topic_id': int(topic.id),
            'title': topic.title,
            'status': topic.status,
            'source': 'manual',
            'message': 'Đã thêm topic thủ công',
        },
        'error': None,
    }


@router.post('/documents/{document_id}/topics/approve-all')
def approve_all_document_topics(
    request: Request,
    document_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    doc = db.query(Document).filter(Document.id == int(document_id)).first()
    if not doc:
        raise HTTPException(status_code=404, detail='Document not found')
    if int(doc.user_id) != int(getattr(teacher, 'id')):
        raise HTTPException(status_code=403, detail='Not allowed')

    now = datetime.now(timezone.utc)
    topics = db.query(DocumentTopic).filter(DocumentTopic.document_id == int(document_id)).all()
    for t in topics:
        t.status = 'approved'
        t.reviewed_at = now
        db.add(t)
    db.commit()

    return {
        'request_id': request.state.request_id,
        'data': {
            'document_id': int(document_id),
            'approved_count': len(topics),
        },
        'error': None,
    }


@router.put('/documents/{document_id}/topics/{topic_id}')
def update_document_topic(
    request: Request,
    document_id: int,
    topic_id: int,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    return review_document_topic(
        request=request,
        document_id=document_id,
        topic_id=topic_id,
        payload={'title': payload.get('title'), 'status': payload.get('status') or 'edited'},
        db=db,
        teacher=teacher,
    )

def _parse_tags(tags: Optional[str]) -> list[str]:
    if not tags:
        return []
    raw = tags.strip()
    if raw.lower() in {"string", "null", "none"}:
        return []
    out: list[str] = []
    for t in raw.split(","):
        tt = t.strip()
        if not tt:
            continue
        if tt.lower() in {"string", "null", "none"}:
            continue
        out.append(tt)
    return out


def _normalize_tags_input(tags: Any) -> list[str]:
    """Accept tags in either JSON array or comma-separated string."""
    if tags is None:
        return []
    if isinstance(tags, list):
        out: list[str] = []
        for x in tags:
            s = str(x).strip()
            if not s or s.lower() in {"string", "null", "none"}:
                continue
            out.append(s)
        return out
    if isinstance(tags, str):
        return _parse_tags(tags)
    # unknown type -> empty
    return []


@router.put('/documents/{document_id}')
def update_document(
    request: Request,
    document_id: int,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    """Update document metadata (title/tags).

    Teacher-only and only on their own documents.
    """
    doc = db.query(Document).filter(Document.id == int(document_id)).first()
    if not doc:
        raise HTTPException(status_code=404, detail='Document not found')
    if int(doc.user_id) != int(getattr(teacher, 'id')):
        raise HTTPException(status_code=403, detail='Not allowed')

    if isinstance(payload, dict):
        if 'title' in payload and payload.get('title') is not None:
            t = str(payload.get('title') or '').strip()
            if not t:
                raise HTTPException(status_code=422, detail='Title cannot be empty')
            doc.title = t[:255]
        if 'tags' in payload:
            doc.tags = _normalize_tags_input(payload.get('tags'))

    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        'request_id': request.state.request_id,
        'data': {
            'document_id': doc.id,
            'title': doc.title,
            'filename': doc.filename,
            'mime_type': doc.mime_type,
            'tags': doc.tags or [],
        },
        'error': None,
    }


@router.delete('/documents/{document_id}')
def delete_document(
    request: Request,
    document_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    """Delete a document and its dependent rows (chunks/topics/legacy quizzes).

    NOTE: DB FKs don't use ON DELETE CASCADE in this repo, so we delete children first.
    """
    doc = db.query(Document).filter(Document.id == int(document_id)).first()
    if not doc:
        raise HTTPException(status_code=404, detail='Document not found')
    if int(doc.user_id) != int(getattr(teacher, 'id')):
        raise HTTPException(status_code=403, detail='Not allowed')

    # Delete children first
    legacy_quizzes_count = (
        db.query(QuizLegacy)
        .filter(QuizLegacy.document_id == int(document_id))
        .delete(synchronize_session=False)
    )
    topics_count = (
        db.query(DocumentTopic)
        .filter(DocumentTopic.document_id == int(document_id))
        .delete(synchronize_session=False)
    )
    chunks_count = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == int(document_id))
        .delete(synchronize_session=False)
    )

    db.delete(doc)
    db.commit()

    vector_info: dict[str, Any] = {'vector_rebuilt': False}
    if vector_store.is_enabled():
        try:
            info = vector_store.rebuild_from_db(db)
            vector_info = {'vector_rebuilt': True, **info}
        except Exception as e:
            vector_info = {'vector_rebuilt': False, 'vector_error': str(e)}

    return {
        'request_id': request.state.request_id,
        'data': {
            'deleted': True,
            'document_id': int(document_id),
            'removed_chunks': int(chunks_count or 0),
            'removed_topics': int(topics_count or 0),
            'removed_legacy_quizzes': int(legacy_quizzes_count or 0),
            **vector_info,
        },
        'error': None,
    }




@router.post("/documents/{document_id}/question-bank/generate")
def generate_question_bank(
    request: Request,
    document_id: int,
    payload: QuestionBankGenerateRequest,
    db: Session = Depends(get_db),
    _teacher: User = Depends(require_teacher),
):
    """Teacher: generate a question bank for ALL topics in a document.

    For each topic, generate >= N questions per difficulty level.
    """
    ensure_user_exists(db, int(payload.user_id), role="teacher")

    topics_q = (
        db.query(DocumentTopic)
        .filter(DocumentTopic.document_id == int(document_id))
        .order_by(DocumentTopic.topic_index.asc())
    )
    if payload.topic_ids:
        topics_q = topics_q.filter(DocumentTopic.id.in_([int(x) for x in payload.topic_ids]))
    topics = topics_q.all()

    levels = list(payload.levels or ["beginner", "intermediate", "advanced"])
    per_level = int(payload.question_count_per_level or 10)
    rag_top_k = int(payload.rag_top_k or 6)

    results = []
    for t in topics:
        for lvl in levels:
            qpayload = QuizGenerateRequest(
                user_id=int(payload.user_id),
                topic=str(t.title),
                level=str(lvl),  # type: ignore[arg-type]
                question_count=per_level,
                rag={
                    "query": str(t.title),
                    "top_k": rag_top_k,
                    "filters": {"document_ids": [int(document_id)]},
                },
            )
            data = generate_quiz_with_rag(db=db, payload=qpayload)
            results.append(
                {
                    "topic_id": int(t.id),
                    "topic": str(t.title),
                    "level": str(lvl),
                    "quiz_id": int(data.get("quiz_id") or 0),
                    "question_count": len(data.get("questions") or []),
                }
            )

    return {
        "request_id": request.state.request_id,
        "data": {
            "document_id": int(document_id),
            "topic_count": len(topics),
            "levels": levels,
            "question_count_per_level": per_level,
            "results": results,
        },
        "error": None,
    }


@router.get('/documents/{document_id}/status')
def get_document_status(
    request: Request,
    document_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    doc = (
        db.query(Document)
        .filter(Document.id == int(document_id))
        .filter(Document.user_id == int(getattr(teacher, "id")))
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail='Document not found')

    status_row = DOCUMENT_PROCESS_STATUS.get(int(document_id))
    topic_count = int(
        db.query(func.count(DocumentTopic.id)).filter(DocumentTopic.document_id == int(document_id)).scalar() or 0
    )
    if status_row:
        return {
            'request_id': request.state.request_id,
            'data': {
                'status': status_row['status'],
                'progress_pct': int(status_row['progress_pct']),
                'topic_count': max(topic_count, int(status_row['topic_count'])),
            },
            'error': None,
        }

    if topic_count > 0:
        derived = {'status': 'ready', 'progress_pct': 100, 'topic_count': topic_count}
    else:
        has_chunks = db.query(func.count(DocumentChunk.id)).filter(DocumentChunk.document_id == int(document_id)).scalar() or 0
        derived = {'status': 'processing' if has_chunks else 'pending', 'progress_pct': 50 if has_chunks else 0, 'topic_count': 0}

    return {'request_id': request.state.request_id, 'data': derived, 'error': None}


async def process_document_pipeline(
    document_id: int,
    user_id: int,
    *,
    filename: str,
    mime_type: str,
    title: str,
    tags: list[str],
    file_bytes: bytes,
) -> None:
    db = SessionLocal()
    _set_doc_status(document_id, status='processing', progress_pct=10, topic_count=0)
    try:
        upload_file = UploadFile(filename=filename, file=BytesIO(file_bytes), headers={'content-type': mime_type})
        full_text, chunks, pdf_report = await extract_and_chunk_with_report(upload_file)

        doc = db.query(Document).filter(Document.id == int(document_id)).first()
        if not doc:
            raise RuntimeError('Document not found')
        doc.content = full_text or ''
        doc.title = title or filename or 'Untitled'
        doc.tags = tags
        doc.mime_type = mime_type or 'application/octet-stream'

        chunk_models = []
        for idx, ch in enumerate(chunks):
            chunk_models.append(
                DocumentChunk(
                    document_id=doc.id,
                    chunk_index=idx,
                    text=ch['text'],
                    meta={
                        **(ch.get('meta') or {}),
                        'hash': hashlib.sha1(' '.join(str(ch['text']).split()).encode('utf-8', errors='ignore')).hexdigest(),
                        'char_len': len(str(ch['text'])),
                    },
                )
            )
        db.add_all(chunk_models)
        db.commit()
        _set_doc_status(document_id, status='processing', progress_pct=55, topic_count=0)

        topic_models: list[DocumentTopic] = []
        try:
            topic_obj = _extract_topics_doc_auto(
                full_text,
                [c.get('text') or '' for c in chunks],
                mime_type=str(getattr(doc, 'mime_type', '') or ''),
                filename=str(getattr(doc, 'filename', '') or ''),
                include_details=True,
                max_topics=int(getattr(settings, 'TOPIC_MAX_TOPICS', 60) or 60),
            )
            if str(topic_obj.get('status') or '') == 'OK':
                topics = topic_obj.get('topics') or []
                ranges = []
                if topics and topics[0].get('start_chunk_index') is not None and topics[0].get('end_chunk_index') is not None:
                    for t in topics:
                        ranges.append((t.get('start_chunk_index'), t.get('end_chunk_index')))
                else:
                    ranges = assign_topic_chunk_ranges(topics, chunk_lengths=[len(c.text or '') for c in chunk_models])

                for i, (t, (s_idx, e_idx)) in enumerate(zip(topics, ranges)):
                    cleaned_title, title_warnings = validate_and_clean_topic_title(str(t.get('title') or '').strip()[:255])
                    page_start, page_end = _infer_page_range_from_chunks(chunk_models, s_idx, e_idx)
                    topic_models.append(
                        DocumentTopic(
                            document_id=doc.id,
                            is_confirmed=False,
                            topic_index=i,
                            title=(cleaned_title or str(t.get('title') or '').strip())[:255],
                            display_title=(cleaned_title or str(t.get('title') or '').strip())[:255],
                            needs_review=bool(t.get('needs_review') or title_warnings),
                            extraction_confidence=float(t.get('extraction_confidence') or 0.0),
                            summary=str(t.get('summary') or '').strip(),
                            keywords=[str(x).strip() for x in (t.get('keywords') or []) if str(x).strip()],
                            start_chunk_index=s_idx,
                            end_chunk_index=e_idx,
                            page_start=page_start,
                            page_end=page_end,
                        )
                    )
        except Exception:
            topic_models = []

        if topic_models:
            db.add_all(topic_models)
            db.commit()

        _set_doc_status(document_id, status='processing', progress_pct=85, topic_count=len(topic_models))

        if vector_store.is_enabled():
            try:
                if is_async_enabled():
                    enqueue(task_index_document, int(doc.id), queue_name='index')
                else:
                    payload_chunks = [{'chunk_id': c.id, 'document_id': c.document_id, 'text': c.text} for c in chunk_models]
                    vector_store.add_chunks(payload_chunks)
            except Exception:
                pass

        _set_doc_status(document_id, status='ready', progress_pct=100, topic_count=len(topic_models))
    except Exception:
        _set_doc_status(document_id, status='error', progress_pct=100, topic_count=0)
    finally:
        db.close()


@router.post('/documents/upload')
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
    file: UploadFile = File(...),
    user_id: int = Form(1),
    title: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
):
    # Ignore user_id from form; use authenticated (demo header) teacher.
    user_id = int(getattr(teacher, 'id'))
    ensure_user_exists(db, int(user_id), role='teacher')

    data = await file.read()
    if not data.startswith(b'%PDF'):
        raise HTTPException(status_code=422, detail='File không phải PDF hợp lệ')

    parsed_tags = _parse_tags(tags)
    safe_title = (title or file.filename or 'Untitled').strip() or 'Untitled'
    doc = Document(
        user_id=user_id,
        title=safe_title,
        content='',
        filename=file.filename or 'unknown.pdf',
        mime_type=file.content_type or 'application/pdf',
        tags=parsed_tags,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    _set_doc_status(doc.id, status='pending', progress_pct=0, topic_count=0)
    background_tasks.add_task(
        process_document_pipeline,
        int(doc.id),
        int(user_id),
        filename=doc.filename,
        mime_type=doc.mime_type,
        title=safe_title,
        tags=parsed_tags,
        file_bytes=data,
    )

    page_count = 0
    if data:
        page_count = data.count(b'/Type /Page')

    return {
        'request_id': request.state.request_id,
        'data': {
            'doc_id': int(doc.id),
            'filename': doc.filename,
            'page_count': int(page_count),
            'status': 'processing',
        },
        'error': None,
    }


@router.put('/documents/{document_id}')
def update_document(
    request: Request,
    document_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    """Edit document metadata (title/tags).

    Payload supports:
      - title: str
      - tags: list[str] | comma-separated str
    """

    doc = (
        db.query(Document)
        .filter(Document.id == int(document_id))
        .filter(Document.user_id == int(getattr(teacher, "id")))
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    title = payload.get("title")
    if title is not None:
        t = str(title).strip()
        if not t:
            raise HTTPException(status_code=400, detail="title cannot be empty")
        doc.title = t[:255]

    tags = payload.get("tags")
    if tags is not None:
        if isinstance(tags, list):
            out_tags: list[str] = []
            for x in tags:
                s = str(x).strip()
                if not s:
                    continue
                if s.lower() in {"string", "null", "none"}:
                    continue
                out_tags.append(s)
            doc.tags = out_tags
        else:
            doc.tags = _parse_tags(str(tags))

    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "request_id": request.state.request_id,
        "data": {
            "document_id": doc.id,
            "title": doc.title,
            "filename": doc.filename,
            "mime_type": doc.mime_type,
            "tags": doc.tags or [],
        },
        "error": None,
    }


@router.delete('/documents/{document_id}')
def delete_document(
    request: Request,
    document_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
):
    """Delete a document and all dependent rows.

    We manually delete children to avoid FK constraint failures.
    """

    doc = (
        db.query(Document)
        .filter(Document.id == int(document_id))
        .filter(Document.user_id == int(getattr(teacher, "id")))
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Count dependents
    chunk_q = db.query(DocumentChunk).filter(DocumentChunk.document_id == int(document_id))
    topic_q = db.query(DocumentTopic).filter(DocumentTopic.document_id == int(document_id))
    legacy_q = db.query(QuizLegacy).filter(QuizLegacy.document_id == int(document_id))

    chunks_count = int(chunk_q.count())
    topics_count = int(topic_q.count())
    legacy_quiz_count = int(legacy_q.count())

    # Delete dependents first
    legacy_q.delete(synchronize_session=False)
    topic_q.delete(synchronize_session=False)
    chunk_q.delete(synchronize_session=False)
    db.delete(doc)
    db.commit()

    vector_info = {"vector_rebuilt": False}
    if vector_store.is_enabled():
        try:
            if is_async_enabled():
                job = enqueue(task_rebuild_vector_index, queue_name="index")
                vector_info = {"vector_rebuilt": False, "queued": True, **job}
            else:
                info = vector_store.rebuild_from_db(db)
                vector_info = {"vector_rebuilt": True, **info}
        except Exception as e:
            vector_info = {"vector_rebuilt": False, "vector_error": str(e)}

    return {
        "request_id": request.state.request_id,
        "data": {
            "deleted": True,
            "document_id": int(document_id),
            "removed_chunks": chunks_count,
            "removed_topics": topics_count,
            "removed_legacy_quizzes": legacy_quiz_count,
            **vector_info,
        },
        "error": None,
    }
