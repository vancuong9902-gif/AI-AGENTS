from app.services.final_exam_novelty_enforcer import _normalize_stem, enforce_final_exam_novelty


def test_normalize_stem_removes_prefix_and_noise():
    assert _normalize_stem("  Câu 1:   Hàm số là gì? ") == "hàm số là gì?"


def test_duplicate_detection_and_regenerate_status():
    payload = {
        "selected_topics": ["Algebra", "Geometry"],
        "difficulty": {"easy": 1, "medium": 1, "hard": 0},
        "candidate_questions": [
            {
                "id": "q1",
                "difficulty": "easy",
                "type": "mcq",
                "stem": "Câu 1: What is a linear equation?",
                "options": ["A", "B", "C", "D"],
                "correct_index": 0,
                "explanation": "An equation of degree one.",
                "topic": "Algebra",
            },
            {
                "id": "q2",
                "difficulty": "medium",
                "type": "mcq",
                "stem": "Find the area of a rectangle with sides 3 and 4.",
                "options": ["7", "12", "14", "16"],
                "correct_index": 1,
                "explanation": "Area = length x width.",
                "topic": "Geometry",
            },
        ],
        "history_stems": {
            "placement": ["What is a linear equation"],
            "assigned_homework": [],
            "practice_sets": [],
            "tutor_quick_checks": [],
        },
        "similarity_threshold": 0.75,
    }

    out = enforce_final_exam_novelty(payload)

    assert out["status"] == "REGENERATE"
    assert len(out["data"]["removed_as_duplicate"]) == 1
    assert out["data"]["removed_as_duplicate"][0]["id"] == "q1"


def test_need_more_materials_when_regen_needed_and_no_book_materials():
    payload = {
        "selected_topics": ["TopicA"],
        "difficulty": {"easy": 1, "medium": 0, "hard": 0},
        "candidate_questions": [
            {
                "id": "q1",
                "difficulty": "easy",
                "type": "mcq",
                "stem": "Question 1: Same old stem",
                "options": ["A", "B", "C", "D"],
                "correct_index": 0,
                "explanation": "Ungrounded explanation",
                "topic": "TopicA",
            }
        ],
        "history_stems": {
            "placement": ["same old stem"],
            "assigned_homework": [],
            "practice_sets": [],
            "tutor_quick_checks": [],
        },
        "similarity_threshold": 0.75,
        "require_book_grounding": True,
    }

    out = enforce_final_exam_novelty(payload)

    assert out["status"] == "NEED_MORE_MATERIALS"
