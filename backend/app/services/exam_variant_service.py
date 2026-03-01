from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from app.services import assessment_service
from app.services.exam_exporters import export_assessment_to_docx


def _stem_signature(questions: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for q in questions or []:
        stem = str(q.get("stem") or "").strip().lower()
        if stem:
            out.add(stem)
    return out


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a.intersection(b))
    union = len(a.union(b))
    return float(inter / union) if union else 0.0


def generate_variants_batch(
    db,
    *,
    teacher_id: int,
    classroom_id: int,
    title_prefix: str,
    level: str,
    kind: str,
    n_variants: int,
    easy_count: int,
    medium_count: int,
    hard_count: int,
    document_ids: list[int],
    topics: list[str],
    exclude_assessment_ids: list[int],
    similarity_threshold: float,
) -> dict[str, Any]:
    generated: list[dict[str, Any]] = []
    signatures: list[set[str]] = []
    exclude_ids = [int(x) for x in (exclude_assessment_ids or [])]

    for idx in range(1, int(n_variants) + 1):
        assessment = assessment_service.generate_assessment(
            db,
            teacher_id=int(teacher_id),
            classroom_id=int(classroom_id),
            title=f"{title_prefix} #{idx}",
            level=level,
            kind=kind,
            easy_count=int(easy_count),
            medium_count=int(medium_count),
            hard_count=int(hard_count),
            document_ids=document_ids,
            topics=topics,
            exclude_quiz_ids=exclude_ids,
            similarity_threshold=float(similarity_threshold),
        )
        sig = _stem_signature(assessment.get("questions") or [])
        max_sim = 0.0
        if signatures:
            max_sim = max(_jaccard(sig, prev) for prev in signatures)
        if max_sim >= float(similarity_threshold):
            raise ValueError(f"Variant {idx} too similar to previous variants (similarity={max_sim:.2f})")

        signatures.append(sig)
        exclude_ids.append(int(assessment["assessment_id"]))
        generated.append({"assessment_id": int(assessment["assessment_id"]), "title": assessment.get("title", ""), "max_similarity": max_sim})

    digest_payload = json.dumps([g["assessment_id"] for g in generated], ensure_ascii=False)
    batch_id = hashlib.sha1(digest_payload.encode("utf-8")).hexdigest()[:16]
    return {"batch_id": batch_id, "variants": generated}


def export_variants_zip(db, *, batch_id: str, assessment_ids: list[int]) -> str:
    tmp = Path(tempfile.mkdtemp(prefix=f"variants_{batch_id}_"))
    zip_path = tmp / f"{batch_id}.zip"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        answer_lines = ["assessment_id,question_id,correct_answer_index"]
        for aid in assessment_ids:
            assessment = assessment_service.get_assessment(db, assessment_id=int(aid))
            docx_path = export_assessment_to_docx(assessment)
            zf.write(docx_path, arcname=f"assessment_{aid}.docx")
            for q in assessment.get("questions") or []:
                if str(q.get("type") or "").lower() == "mcq":
                    answer_lines.append(f"{aid},{int(q.get('question_id') or 0)},{int(q.get('correct_index', 0) or 0)}")

        answer_file = tmp / "answers.csv"
        answer_file.write_text("\n".join(answer_lines), encoding="utf-8")
        zf.write(answer_file, arcname="answers.csv")

    return str(zip_path)
