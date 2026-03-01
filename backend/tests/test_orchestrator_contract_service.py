from app.services.orchestrator_contract_service import (
    make_need_clean_text_response,
    make_orchestrator_response,
    needs_clean_text,
)


def test_needs_clean_text_detects_mojibake():
    assert needs_clean_text([
        "ChÆ°Æ¡ng 1: HÃ m sá»‘ báº­c nháº¥t",
        "Ná»™i dung bá»‹ vá»¡ font do OCR sai",
        "Một đoạn đúng nhưng quá ngắn",
    ]) is True


def test_make_need_clean_text_response_schema():
    out = make_need_clean_text_response()
    assert out["status"] == "NEED_CLEAN_TEXT"
    assert out["action"] == "validate_input"
    assert isinstance(out["data"], dict)
    assert isinstance(out["next_steps"], list)


def test_make_orchestrator_response_normalizes_shape():
    out = make_orchestrator_response(
        action="placement_generate",
        message="  Tạo đề đầu vào theo topic đã chọn.  ",
        data={"topics": ["Hàm số bậc nhất"]},
        next_steps=["Chọn thời lượng", "Bắt đầu làm bài"],
    )
    assert out == {
        "status": "OK",
        "action": "placement_generate",
        "message": "Tạo đề đầu vào theo topic đã chọn.",
        "data": {"topics": ["Hàm số bậc nhất"]},
        "next_steps": ["Chọn thời lượng", "Bắt đầu làm bài"],
    }
