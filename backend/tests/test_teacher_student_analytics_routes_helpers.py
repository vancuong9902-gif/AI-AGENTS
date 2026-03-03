from app.api.routes.analytics import _score_ranges


def test_score_ranges_distribution():
    rows = _score_ranges([0, 20, 21, 40, 41, 60, 61, 80, 81, 100])
    assert rows == [
        {"range": "0-20", "count": 2},
        {"range": "21-40", "count": 2},
        {"range": "41-60", "count": 2},
        {"range": "61-80", "count": 2},
        {"range": "81-100", "count": 2},
    ]
