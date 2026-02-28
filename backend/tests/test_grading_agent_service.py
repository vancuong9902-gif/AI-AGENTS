from app.services.grading_agent_service import grade_submission


def test_grade_submission_mcq_and_essay_with_evidence():
    questions = [
        {
            "question_id": 1,
            "topic": "Algebra",
            "difficulty": "easy",
            "bloom_level": "remember",
            "max_points": 2,
            "correct": "B",
            "sources": ["src1"],
        },
        {
            "question_id": 2,
            "topic": "Algebra",
            "difficulty": "medium",
            "bloom_level": "apply",
            "max_points": 4,
            "rubric": [
                {"criterion": "Nêu khái niệm", "points": 2, "keywords": ["hàm số", "biến"]},
                {"criterion": "Nêu ví dụ", "points": 2, "keywords": ["y=2x+1"]},
            ],
            "sources": ["src1"],
        },
    ]
    student_answers = {
        "1": "B",
        "2": "Hàm số có biến. Ví dụ y=2x+1",
    }
    evidence_chunks = {
        "src1": [
            {"text": "Hàm số thể hiện quan hệ giữa biến x và y."},
            {"text": "Ví dụ cơ bản: y=2x+1."},
        ]
    }

    out = grade_submission(
        questions=questions,
        student_answers=student_answers,
        evidence_chunks=evidence_chunks,
        scoring_policy={"mcq_exact": True, "essay_rubric": True},
    )

    assert out["total_points"] == 6
    assert out["earned_points"] == 6
    assert out["score_percent"] == 100
    assert out["by_topic"]["Algebra"]["percent"] == 100.0


def test_grade_submission_essay_outside_material_note():
    questions = [
        {
            "question_id": 1,
            "topic": "Physics",
            "difficulty": "hard",
            "bloom_level": "analyze",
            "max_points": 4,
            "rubric": [
                {"criterion": "Định luật", "points": 4, "keywords": ["newton", "gia tốc"]}
            ],
            "sources": ["srcA"],
        }
    ]
    student_answers = [{"question_id": 1, "answer": "Newton và mô men xoắn"}]
    evidence_chunks = {"srcA": [{"text": "Tài liệu đề cập đến lực và gia tốc."}]}

    out = grade_submission(
        questions=questions,
        student_answers=student_answers,
        evidence_chunks=evidence_chunks,
        scoring_policy={"mcq_exact": True, "essay_rubric": True},
    )

    assert out["earned_points"] < out["total_points"]
    assert "ngoài tài liệu" in out["breakdown"][0]["comment"].lower()
