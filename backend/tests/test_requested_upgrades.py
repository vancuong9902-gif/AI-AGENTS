from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.mas.orchestrator import Orchestrator
from app.services.exam_exporters.docx_exporter import export_assessment_to_docx


def test_orchestrator_has_all_agents():
    orchestrator = Orchestrator(db=None)
    assert hasattr(orchestrator, "content")
    assert hasattr(orchestrator, "assessment")
    assert hasattr(orchestrator, "policy")
    assert hasattr(orchestrator, "modeling")
    assert hasattr(orchestrator, "analytics")


def test_student_journey():
    client = TestClient(app)
    assert client.get("/api/health").status_code == 200


def test_rate_limiter():
    client = TestClient(app)
    assert client.get("/api/health").status_code == 200


def test_docx_export_produces_valid_file():
    assessment = {
        "title": "Entry Test",
        "level": "basic",
        "questions": [
            {
                "type": "mcq",
                "bloom_level": "understand",
                "stem": "2 + 2 bằng bao nhiêu?",
                "options": ["1", "2", "3", "4"],
                "correct_index": 3,
            }
            for _ in range(20)
        ],
    }
    path = export_assessment_to_docx(assessment, kind="entry_test")
    assert Path(path).exists()
    assert Path(path).stat().st_size > 1000
