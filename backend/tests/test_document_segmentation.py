from app.services.document_pipeline import _chunk_text


def test_chunk_text_detects_all_caps_and_blankline_headings_without_wrong_merge():
    text = """
GIỚI HẠN

Khái niệm giới hạn của hàm số mô tả xu hướng khi biến tiến tới một giá trị xác định.


DAO HAM

Định nghĩa
Đạo hàm thể hiện tốc độ thay đổi tức thời của hàm số tại một điểm.
Ví dụ: đạo hàm của x^2 là 2x.


3) Quy tắc đạo hàm

Bài tập
Tính đạo hàm của các hàm đa thức cơ bản.
""".strip()

    chunks = _chunk_text(text, chunk_size=700, overlap=100)

    assert chunks
    assert any("GIỚI HẠN" in c for c in chunks)
    assert any("DAO HAM" in c for c in chunks)
    assert any("3) Quy tắc đạo hàm" in c for c in chunks)
    assert len(chunks) >= 3


def test_chunk_text_supports_markdown_and_hierarchical_number_headings():
    text = """
# Unit 5

Introduction to probability distributions.

1.2.3 Conditional probability

Summary
Important formulas and examples.
""".strip()

    chunks = _chunk_text(text, chunk_size=620, overlap=90)

    assert chunks
    assert any("# Unit 5" in c for c in chunks)
    assert any("1.2.3 Conditional probability" in c for c in chunks)
    assert any("Summary" in c for c in chunks)
