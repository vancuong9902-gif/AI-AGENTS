from app.services.adaptive_engine import AdaptiveEngine, LearnerSignal


def test_mastery_delta_fast_correct() -> None:
    assert AdaptiveEngine.mastery_delta(correct=True, response_time_seconds=9.9) == 2


def test_mastery_delta_slow_correct() -> None:
    assert AdaptiveEngine.mastery_delta(correct=True, response_time_seconds=10.0) == 1


def test_mastery_delta_incorrect() -> None:
    assert AdaptiveEngine.mastery_delta(correct=False, response_time_seconds=2.0) == -2


def test_update_improves_ability_on_correct_answer() -> None:
    engine = AdaptiveEngine()
    result = engine.update(
        LearnerSignal(
            ability=1200.0,
            question_difficulty=1250.0,
            correct=True,
            response_time_seconds=8.5,
        )
    )

    assert result.mastery_delta == 2
    assert result.new_ability > 1200.0
    assert result.next_recommended_difficulty >= 1200.0


def test_update_reduces_ability_on_incorrect_answer() -> None:
    engine = AdaptiveEngine()
    result = engine.update(
        LearnerSignal(
            ability=1500.0,
            question_difficulty=1450.0,
            correct=False,
            response_time_seconds=6.2,
        )
    )

    assert result.mastery_delta == -2
    assert result.new_ability < 1500.0
