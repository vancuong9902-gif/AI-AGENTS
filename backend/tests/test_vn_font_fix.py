from app.services.vietnamese_font_fix import detect_broken_vn_font, fix_vietnamese_font_encoding


def fix_vn(text: str) -> str:
    return fix_vietnamese_font_encoding(text)


def test_01() -> None:
    assert detect_broken_vn_font('To¸n häc') is True


def test_02() -> None:
    assert detect_broken_vn_font('Toán học') is False


def test_03() -> None:
    assert detect_broken_vn_font('Hello World') is False


def test_04() -> None:
    assert fix_vn('To¸n häc') == 'Toán học'


def test_05() -> None:
    assert fix_vn('Ph\xad¬ng tr×nh bËc hai') == 'Phương trình bậc hai'


def test_06() -> None:
    assert fix_vn('®¹o hµm') == 'đạo hàm'


def test_07() -> None:
    assert fix_vn('c¸c kh¸i niÖm') == 'các khái niệm'


def test_08() -> None:
    assert fix_vn('') == ''


def test_09() -> None:
    assert fix_vn('x² + y² = z²') == 'x² + y² = z²'


def test_10() -> None:
    assert fix_vn('Normal UTF-8 text') == 'Normal UTF-8 text'
