import io
import zipfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user_optional, get_db
from app.api.routes.exams import router as exams_router

app = FastAPI()
app.include_router(exams_router, prefix="/api")


class _FakeDB:
    pass


def test_batch_generate_zip(monkeypatch, tmp_path: Path):
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    app.dependency_overrides[get_current_user_optional] = lambda: None

    counter = {"value": 0}
    exclude_args = []

    def _fake_generate_assessment(db, **kwargs):
        exclude_args.append(list(kwargs.get("exclude_quiz_ids") or []))
        idx = counter["value"]
        counter["value"] += 1
        return {
            "assessment_id": 100 + idx,
            "title": kwargs.get("title", "Paper"),
            "questions": [
                {
                    "type": "mcq",
                    "stem": f"Question {idx}-1",
                    "options": ["A1", "B1", "C1", "D1"],
                    "correct_index": 1,
                },
                {
                    "type": "mcq",
                    "stem": f"Question {idx}-2",
                    "options": ["A2", "B2", "C2", "D2"],
                    "correct_index": 2,
                },
                {
                    "type": "essay",
                    "stem": f"Essay {idx}",
                    "max_points": 5,
                },
            ],
        }

    monkeypatch.setattr("app.api.routes.exams.assessment_service.generate_assessment", _fake_generate_assessment)

    client = TestClient(app)
    res = client.post(
        "/api/exams/batch-generate",
        json={
            "teacher_id": 1,
            "classroom_id": 2,
            "title": "Batch Print",
            "num_papers": 3,
            "questions_per_paper": 12,
            "mcq_ratio": 0.7,
            "difficulty_distribution": {"easy": 0.3, "medium": 0.4, "hard": 0.3},
            "include_answer_key": True,
            "paper_code_style": "ABC",
        },
    )

    assert res.status_code == 200
    assert "application/zip" in res.headers.get("content-type", "")

    archive_path = tmp_path / "batch.zip"
    archive_path.write_bytes(res.content)
    assert archive_path.exists()

    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        names = zf.namelist()
        paper_files = sorted([n for n in names if n.startswith("paper_") and n.endswith(".docx")])
        assert len(paper_files) == 3
        assert "answer_key.docx" in names
        assert "metadata.json" in names

    assert len(set(paper_files)) == 3
    assert exclude_args[0] == []
    assert exclude_args[1] == [100]
    assert exclude_args[2] == [100, 101]

    app.dependency_overrides.clear()
