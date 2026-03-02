from types import SimpleNamespace

from app.services import adaptive_policy_service as s


def test_build_state_defaults_and_bins():
    profile = SimpleNamespace(mastery_json={"mastery": 0.9}, level="medium")
    out = s.build_state(profile=profile, topic="", recent_accuracy=None, avg_time_per_item_sec=None, engagement=None, current_difficulty=None)
    assert out["topic"] == "__global__"
    assert out["bins"]["difficulty"] == 1


def test_sherman_morrison_no_change_when_zero_vector():
    ainv = [[1.0, 0.0], [0.0, 1.0]]
    s._sherman_morrison_update(ainv, [0.0, 0.0])
    assert ainv == [[1.0, 0.0], [0.0, 1.0]]
