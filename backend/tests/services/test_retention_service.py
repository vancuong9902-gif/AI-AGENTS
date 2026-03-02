from app.services import retention_service as s


def test_fit_forgetting_lambda_empty_points():
    out = s._fit_forgetting_lambda(0.8, [])
    assert out["lambda"] is None


def test_retention_reward_clamped():
    out = s._retention_reward(baseline_score_percent=10, retention_score_percent=100, interval_days=30)
    assert -1 <= out["reward"] <= 1
