from app.services import assessment_service as s


def test_parse_duration_seconds_parses_valid_text():
    assert s.parse_duration_seconds("intermediate;duration=2700") == 2700


def test_parse_duration_seconds_none_for_invalid():
    assert s.parse_duration_seconds("abc") is None
