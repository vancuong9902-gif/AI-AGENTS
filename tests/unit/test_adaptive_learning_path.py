import pytest

from app.application.use_cases.adaptive_learning_path import create_adaptive_learning_path


CURRICULUM = [
    "Python Basics",
    "Data Structures",
    "Algorithms",
    "System Design",
]


def test_beginner_gets_full_curriculum() -> None:
    result = create_adaptive_learning_path(level="beginner", curriculum=CURRICULUM)

    assert [item["topic"] for item in result["learning_path"]] == CURRICULUM
    assert all(item["exercise_count"] == 4 for item in result["learning_path"])


def test_intermediate_skips_mastered_topics() -> None:
    result = create_adaptive_learning_path(
        level="intermediate",
        curriculum=CURRICULUM,
        mastered_topics=["Python Basics", "Data Structures"],
    )

    assert [item["topic"] for item in result["learning_path"]] == ["Algorithms", "System Design"]


def test_advanced_focuses_on_weak_topics_with_more_exercises() -> None:
    result = create_adaptive_learning_path(
        level="advanced",
        curriculum=CURRICULUM,
        weak_topics=["Algorithms"],
    )

    assert [item["topic"] for item in result["learning_path"]] == ["Algorithms"]
    assert result["learning_path"][0]["exercise_count"] == 6


def test_dynamic_difficulty_adjusts_from_scores() -> None:
    high = create_adaptive_learning_path(
        level="intermediate",
        curriculum=CURRICULUM,
        recent_scores=[0.9, 0.95],
    )
    low = create_adaptive_learning_path(
        level="intermediate",
        curriculum=CURRICULUM,
        recent_scores=[0.4, 0.45],
    )

    assert high["learning_path"][0]["difficulty"] == "hard"
    assert low["learning_path"][0]["difficulty"] == "easy"


def test_invalid_level_raises_error() -> None:
    with pytest.raises(ValueError):
        create_adaptive_learning_path(level="expert", curriculum=CURRICULUM)
