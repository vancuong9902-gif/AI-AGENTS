from app.services.text_repair import clean_ocr_artifacts, has_ocr_artifacts, repair_ocr_spacing_text


def test_clean_ocr_artifacts_removes_replacement_char_and_normalizes_spacing():
    raw = "Đây là ký tự lỗi � trong OCR .  Nội  dung"
    cleaned = clean_ocr_artifacts(raw)
    assert "�" not in cleaned
    assert "OCR." in cleaned
    assert "  " not in cleaned


def test_has_ocr_artifacts_detects_replacement_character():
    assert has_ocr_artifacts("abc�def") is True
    assert has_ocr_artifacts("nội dung bình thường") is False


def test_repair_ocr_spacing_text_runs_artifact_cleanup_end_to_end():
    raw = "Pytho n  �  cơ b ản"
    repaired = repair_ocr_spacing_text(raw)
    assert "�" not in repaired
    assert "Pytho" in repaired
