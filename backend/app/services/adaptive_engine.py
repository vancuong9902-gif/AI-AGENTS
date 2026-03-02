from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LearnerSignal:
    """Signals captured from a learner answer event."""

    ability: float
    question_difficulty: float
    correct: bool
    response_time_seconds: float


@dataclass(frozen=True)
class AdaptiveUpdate:
    """Result of a mastery + ability update."""

    mastery_delta: int
    new_ability: float
    next_recommended_difficulty: float


class AdaptiveEngine:
    """Adaptive mastery and ELO-like question recommendation engine."""

    def __init__(self, *, k_factor: float = 16.0, min_difficulty: float = 200.0, max_difficulty: float = 2800.0) -> None:
        self.k_factor = k_factor
        self.min_difficulty = min_difficulty
        self.max_difficulty = max_difficulty

    @staticmethod
    def mastery_delta(*, correct: bool, response_time_seconds: float) -> int:
        if not correct:
            return -2
        if response_time_seconds < 10.0:
            return 2
        return 1

    @staticmethod
    def _expected_score(ability: float, question_difficulty: float) -> float:
        return 1.0 / (1.0 + 10 ** ((question_difficulty - ability) / 400.0))

    def update(self, signal: LearnerSignal) -> AdaptiveUpdate:
        observed_score = 1.0 if signal.correct else 0.0
        expected_score = self._expected_score(signal.ability, signal.question_difficulty)
        new_ability = signal.ability + self.k_factor * (observed_score - expected_score)

        ability_gap = new_ability - signal.question_difficulty
        next_recommended_difficulty = self._clamp(signal.question_difficulty + (ability_gap * 0.5))

        return AdaptiveUpdate(
            mastery_delta=self.mastery_delta(correct=signal.correct, response_time_seconds=signal.response_time_seconds),
            new_ability=round(new_ability, 4),
            next_recommended_difficulty=round(next_recommended_difficulty, 4),
        )

    def _clamp(self, difficulty: float) -> float:
        return max(self.min_difficulty, min(self.max_difficulty, difficulty))
