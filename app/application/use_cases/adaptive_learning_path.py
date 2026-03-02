from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TopicPlan:
    topic: str
    difficulty: str
    exercise_count: int


def _clamp_difficulty(level: int) -> int:
    return max(1, min(5, level))


def _difficulty_label(level: int) -> str:
    labels = {
        1: "very_easy",
        2: "easy",
        3: "medium",
        4: "hard",
        5: "very_hard",
    }
    return labels[_clamp_difficulty(level)]


def _dynamic_difficulty(base_level: int, recent_scores: list[float] | None) -> int:
    if not recent_scores:
        return _clamp_difficulty(base_level)

    avg_score = sum(recent_scores) / len(recent_scores)
    if avg_score >= 0.85:
        return _clamp_difficulty(base_level + 1)
    if avg_score <= 0.5:
        return _clamp_difficulty(base_level - 1)
    return _clamp_difficulty(base_level)


def create_adaptive_learning_path(
    *,
    level: str,
    curriculum: list[str],
    mastered_topics: list[str] | None = None,
    weak_topics: list[str] | None = None,
    recent_scores: list[float] | None = None,
) -> dict[str, list[dict[str, str | int]]]:
    mastered = set(mastered_topics or [])
    weak = set(weak_topics or [])
    learner_level = level.lower().strip()

    if learner_level == "beginner":
        selected_topics = curriculum
        base_difficulty = 2
        base_exercises = 4
    elif learner_level == "intermediate":
        selected_topics = [topic for topic in curriculum if topic not in mastered]
        base_difficulty = 3
        base_exercises = 3
    elif learner_level == "advanced":
        selected_topics = [topic for topic in curriculum if topic in weak] or curriculum
        base_difficulty = 4
        base_exercises = 5
    else:
        raise ValueError("level must be one of: beginner, intermediate, advanced")

    adjusted_level = _dynamic_difficulty(base_difficulty, recent_scores)
    learning_path = [
        TopicPlan(
            topic=topic,
            difficulty=_difficulty_label(adjusted_level),
            exercise_count=base_exercises + (1 if learner_level == "advanced" else 0),
        )
        for topic in selected_topics
    ]

    return {
        "learning_path": [
            {
                "topic": item.topic,
                "difficulty": item.difficulty,
                "exercise_count": item.exercise_count,
            }
            for item in learning_path
        ]
    }
