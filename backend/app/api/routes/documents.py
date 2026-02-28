from __future__ import annotations

import hashlib

from typing import Optional, Any

from fastapi import APIRouter, Body, Depends, File, Form, Request, UploadFile, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.quiz import QuizGenerateRequest
from app.schemas.question_bank import QuestionBankGenerateRequest
from app.api.deps import get_current_user_optional, require_teacher
from app.models.user import User
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_topic import DocumentTopic
from app.models.quiz import QuizLegacy
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
)
from app.services import vector_store
from app.infra.queue import is_async_enabled, enqueue
from app.tasks.index_tasks import task_index_document, task_rebuild_vector_index
from app.services.user_service import ensure_user_exists
from app.services.quiz_service import generate_quiz_with_rag

router = APIRouter(tags=['documents'])


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
def list_document_topics(request: Request, document_id: int, db: Session = Depends(get_db), detail: int = 0, filter: str | None = None):
    topics_q = db.query(DocumentTopic).filter(DocumentTopic.document_id == document_id)
    if (filter or '').strip().lower() == 'needs_review':
        topics_q = topics_q.filter(DocumentTopic.needs_review.is_(True))
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
            # Frontend can show ordering using topic_index; keep titles clean.
            "display_title": t.display_title or t.title,
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
    return {
        'request_id': request.state.request_id,
        'data': {'document_id': document_id, 'topics': out, 'needs_review_count': needs_review_count},
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
            tm = DocumentTopic(
                document_id=int(document_id),
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
                metadata_json={
                    "original_exercises": (t.get("original_exercises") or []),
                    "has_original_exercises": bool(t.get("has_original_exercises")),
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
                        'display_title': tm.display_title or tm.title,
                        'needs_review': bool(tm.needs_review),
                        'extraction_confidence': float(tm.extraction_confidence or 0.0),
                        'page_range': [tm.page_start, tm.page_end],
                        'summary': tm.summary,
                        'keywords': tm.keywords or [],
                        'has_original_exercises': bool((tm.metadata_json or {}).get('has_original_exercises')),
                        'original_exercise_count': len((tm.metadata_json or {}).get('original_exercises') or []),
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
        "display_title": t.display_title or t.title,
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


@router.put('/documents/{document_id}/topics/{topic_id}')
def update_document_topic(
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

    new_title = str(payload.get('title') or '').strip()
    if not new_title:
        raise HTTPException(status_code=422, detail='Title cannot be empty')

    cleaned, warnings = validate_and_clean_topic_title(new_title)
    topic.title = (cleaned or new_title)[:255]
    topic.display_title = (cleaned or new_title)[:255]
    topic.needs_review = bool(warnings)
    topic.extraction_confidence = max(float(topic.extraction_confidence or 0.0), 0.95)

    db.add(topic)
    db.commit()
    db.refresh(topic)

    return {
        'request_id': request.state.request_id,
        'data': {
            'topic_id': int(topic.id),
            'document_id': int(document_id),
            'title': topic.title,
            'display_title': topic.display_title,
            'needs_review': bool(topic.needs_review),
            'extraction_confidence': float(topic.extraction_confidence or 0.0),
            'page_range': [topic.page_start, topic.page_end],
        },
        'error': None,
    }


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


@router.post('/documents/upload')
async def upload_document(
    request: Request,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_teacher),
    file: UploadFile = File(...),
    user_id: int = Form(1),
    title: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
):
    # Ignore user_id from form; use authenticated (demo header) teacher.
    user_id = int(getattr(teacher, "id"))
    ensure_user_exists(db, int(user_id), role="teacher")

    parsed_tags = _parse_tags(tags)
    full_text, chunks, pdf_report = await extract_and_chunk_with_report(file)

    doc = Document(
        user_id=user_id,
        title=title or file.filename or 'Untitled',
        content=full_text or '',
        filename=file.filename or 'unknown',
        mime_type=file.content_type or 'application/octet-stream',
        tags=parsed_tags,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    chunk_models = []
    for idx, ch in enumerate(chunks):
        chunk_models.append(
            DocumentChunk(
                document_id=doc.id,
                chunk_index=idx,
                text=ch['text'],
                meta={**(ch.get('meta') or {}), 'hash': hashlib.sha1(' '.join(str(ch['text']).split()).encode('utf-8', errors='ignore')).hexdigest(), 'char_len': len(str(ch['text']))},
            )
        )
    db.add_all(chunk_models)
    db.flush()
    db.commit()

    # --- Auto-topic extraction (Content Agent) ---
    topics_payload: list[dict[str, Any]] = []
    topics_status = "SKIPPED"
    topics_reason = None
    topics_quality = None

    try:
        topic_obj = _extract_topics_doc_auto(
            full_text,
            [c.get("text") or "" for c in chunks],
            mime_type=str(getattr(doc, 'mime_type', '') or ''),
            filename=str(getattr(doc, 'filename', '') or ''),
            include_details=True,
            max_topics=int(getattr(settings, 'TOPIC_MAX_TOPICS', 60) or 60),
        )
        topics_quality = topic_obj.get("quality")
        topics_status = str(topic_obj.get("status") or "SKIPPED")
        if topics_status == "OK":
            topics = topic_obj.get("topics") or []

            # Prefer start/end from the extractor (chunk-aware). If absent, fall back to deterministic length-based mapping.
            ranges = []
            if topics and topics[0].get("start_chunk_index") is not None and topics[0].get("end_chunk_index") is not None:
                for t in topics:
                    ranges.append((t.get("start_chunk_index"), t.get("end_chunk_index")))
            else:
                ranges = assign_topic_chunk_ranges(topics, chunk_lengths=[len(c.text or "") for c in chunk_models])

            # IMPORTANT: Keep stored ranges TIGHT for clean topic display.
            # When generating quizzes, we can expand the evidence window on-the-fly.

            topic_models: list[DocumentTopic] = []
            for i, (t, (s_idx, e_idx)) in enumerate(zip(topics, ranges)):
                cleaned_title, title_warnings = validate_and_clean_topic_title(str(t.get("title") or "").strip()[:255])
                page_start, page_end = _infer_page_range_from_chunks(chunk_models, s_idx, e_idx)
                tm = DocumentTopic(
                    document_id=doc.id,
                    topic_index=i,
                    title=(cleaned_title or str(t.get("title") or "").strip())[:255],
                    display_title=(cleaned_title or str(t.get("title") or "").strip())[:255],
                    needs_review=bool(t.get("needs_review") or title_warnings),
                    extraction_confidence=float(t.get("extraction_confidence") or 0.0),
                    summary=str(t.get("summary") or "").strip(),
                    keywords=[str(x).strip() for x in (t.get("keywords") or []) if str(x).strip()],
                    start_chunk_index=s_idx,
                    end_chunk_index=e_idx,
                    page_start=page_start,
                    page_end=page_end,
                    metadata_json={
                        "original_exercises": (t.get("original_exercises") or []),
                        "has_original_exercises": bool(t.get("has_original_exercises")),
                    },
                )
                topic_models.append(tm)

            if topic_models:
                db.add_all(topic_models)
                db.commit()

                # Build response payload with the *same order* as extracted topics.
                for tm, t in zip(topic_models, topics):
                    s_idx = tm.start_chunk_index
                    e_idx = tm.end_chunk_index
                    included_chunk_ids: list[int] = []
                    if s_idx is not None and e_idx is not None and 0 <= int(s_idx) <= int(e_idx) < len(chunk_models):
                        included_chunk_ids = [c.id for c in chunk_models[int(s_idx): int(e_idx) + 1]]

                    chunk_lengths = [len(c.text or "") for c in chunk_models]
                    stats_tight = topic_range_stats(
                        start_chunk_index=s_idx,
                        end_chunk_index=e_idx,
                        chunk_lengths=chunk_lengths,
                    )
                    s2, e2 = (s_idx, e_idx)
                    if s_idx is not None and e_idx is not None:
                        try:
                            (s2, e2) = ensure_topic_chunk_ranges_ready_for_quiz(
                                [(int(s_idx), int(e_idx))],
                                chunk_lengths=chunk_lengths,
                            )[0]
                        except Exception:
                            s2, e2 = (s_idx, e_idx)
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
                            "topic_id": tm.id,
                            "topic_index": tm.topic_index,
                            "title": tm.title,
                            "display_title": tm.display_title or tm.title,
                            "needs_review": bool(tm.needs_review),
                            "extraction_confidence": float(tm.extraction_confidence or 0.0),
                            "page_range": [tm.page_start, tm.page_end],
                            "summary": tm.summary,
                            "keywords": tm.keywords or [],
                            "has_original_exercises": bool((tm.metadata_json or {}).get("has_original_exercises")),
                            "original_exercise_count": len((tm.metadata_json or {}).get("original_exercises") or []),
                            "start_chunk_index": tm.start_chunk_index,
                            "end_chunk_index": tm.end_chunk_index,
                            # richer topic profile (computed during extraction)
                            "outline": (t.get("outline") or []),
                            "key_points": (t.get("key_points") or []),
                            "definitions": (t.get("definitions") or []),
                            "examples": (t.get("examples") or []),
                            "formulas": (t.get("formulas") or []),
                            # Optional: external enrichment for "Ít dữ liệu" topics
                            "sources": (t.get("sources") or []),
                            "external_notes": (t.get("external_notes") or []),
                            "content_preview": t.get("content_preview"),
                            "content_len": t.get("content_len"),
                            "has_more_content": t.get("has_more_content"),
                            "included_chunk_ids": included_chunk_ids,
                            "chunk_span": stats_tight.get('chunk_span', 0),
                            "range_char_len": stats_tight.get('char_len', 0),
                            "evidence_chunk_span": stats.get('chunk_span', 0),
                            "evidence_char_len": stats.get('char_len', 0),
                            "quiz_ready": bool(quiz_ready),
                        }
                    )
        else:
            topics_reason = topic_obj.get("reason")
    except Exception as e:
        topics_status = "ERROR"
        topics_reason = str(e)

    # Try to index chunks into FAISS (semantic RAG).
    # IMPORTANT: Semantic RAG is optional for the demo (API billing/quota may be unavailable).
    # When disabled, we skip indexing instead of returning a scary error message.
    vector_info = {"vector_indexed": False}
    if vector_store.is_enabled():
        try:
            # Event-driven infra:
            # - If ASYNC_QUEUE_ENABLED=true and Redis/RQ are available, enqueue indexing.
            # - Otherwise do the synchronous add_chunks (demo-friendly default).
            if is_async_enabled():
                job = enqueue(task_index_document, int(doc.id), queue_name="index")
                vector_info = {"vector_indexed": False, "queued": True, **job}
            else:
                payload_chunks = [{"chunk_id": c.id, "document_id": c.document_id, "text": c.text} for c in chunk_models]
                info = vector_store.add_chunks(payload_chunks)
                vector_info = {"vector_indexed": True, **info}
        except Exception as e:
            vector_info = {"vector_indexed": False, "vector_error": str(e)}
    else:
        vector_info = {"vector_indexed": False, "skipped": True, "reason": "Semantic RAG disabled"}

    return {
        'request_id': request.state.request_id,
        'data': {
            'document_id': doc.id,
            'title': doc.title,
            'filename': doc.filename,
            'mime_type': doc.mime_type,
            'chunk_count': len(chunk_models),
            'topics_status': topics_status,
            'topics_reason': topics_reason,
            'topics_quality': topics_quality,
            'topics': topics_payload,
            'pdf_report': pdf_report,
            **vector_info,
            'vector_status': vector_store.status(),
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
