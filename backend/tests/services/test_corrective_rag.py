from app.services import corrective_rag as s


def test_grade_retrieval_empty_chunks():
    score, min_score, per = s._grade_retrieval("python", [])
    assert score == 0.0 and min_score == 0.0 and per == []


def test_needs_correction_on_low_relevance():
    assert s._needs_correction("python java", [{"text": "go rust"}], min_rel=0.6) is True
