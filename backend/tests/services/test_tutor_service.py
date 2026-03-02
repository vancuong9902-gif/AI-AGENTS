from app.services import tutor_service as s


def test_topic_scope_and_redirect_hint():
    assert s._topic_scope(None) == "môn học hiện tại"
    assert "Hàm số" in s._build_redirect_hint("Hàm số")


def test_practice_request_detection():
    assert s._is_practice_request("hãy đặt câu hỏi cho tôi") is True
