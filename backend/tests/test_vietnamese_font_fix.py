from app.services.vietnamese_font_fix import (
    detect_broken_vn_font,
    fix_vietnamese_font_encoding,
)


def test_utf8_text_unchanged():
    text = "Toán học lớp 10"
    assert fix_vietnamese_font_encoding(text) == text


def test_fix_tcvn3_toan_hoc():
    broken = "Môn To¸n häc rất quan trọng trong chương trình."
    assert fix_vietnamese_font_encoding(broken) == "Môn Toán học rất quan trọng trong chương trình."


def test_fix_tcvn3_phuong_trinh_bac_hai():
    broken = "Bài này nói về Ph\xad¬ng tr×nh bËc hai trong đại số."
    assert fix_vietnamese_font_encoding(broken) == "Bài này nói về Phương trình bậc hai trong đại số."


def test_fix_vntime_specific_case():
    broken = "Trong N¨m häc 2024, học sinh học tích cực hơn."
    assert fix_vietnamese_font_encoding(broken) == "Trong Năm học 2024, học sinh học tích cực hơn."


def test_empty_text_returns_empty():
    assert fix_vietnamese_font_encoding("") == ""


def test_english_text_unchanged():
    text = "This is an English sentence about algebra."
    assert fix_vietnamese_font_encoding(text) == text


def test_mixed_vn_en_text():
    broken = "Môn To¸n học and Physics đều cần tư duy logic."
    assert fix_vietnamese_font_encoding(broken) == "Môn Toán học and Physics đều cần tư duy logic."


def test_keep_math_formula_symbols():
    text = "Công thức: x² + y² = z²"
    assert fix_vietnamese_font_encoding(text) == text


def test_detect_broken_returns_true_for_broken_text():
    text = ("Ph\xad¬ng tr×nh bËc hai " * 3).strip()
    assert detect_broken_vn_font(text) is True


def test_detect_broken_returns_false_for_normal_text():
    text = "Phương trình bậc hai có nghiệm khi delta không âm."
    assert detect_broken_vn_font(text) is False
