from app.services.heuristic_grader import (
    _clarity_score,
    _example_score,
    _extract_keywords,
    _keyword_coverage,
    _structure_score,
    _tokenize,
    grade_essay_heuristic,
)


def test_tokenize_filters_stopwords_and_digits():
    toks = _tokenize("Đây là ví dụ 123 về học máy và data-driven systems")
    assert "123" not in toks
    assert "là" not in toks
    assert "systems" in toks


def test_extract_keywords_and_coverage():
    kws = _extract_keywords(evidence_texts=["gradient descent tối ưu mô hình", "mô hình tuyến tính"], stem="mô hình học máy", top_k=5)
    cov, present, missing = _keyword_coverage("Mô hình tuyến tính dùng gradient", kws)
    assert kws
    assert cov > 0
    assert present
    assert isinstance(missing, list)


def test_structure_example_clarity_scores_have_expected_ranges():
    answer = """1. Đầu tiên xác định dữ liệu.\n2. Sau đó chuẩn hóa dữ liệu vì chất lượng đầu vào quan trọng.\nVí dụ: bộ dữ liệu 2024."""
    assert 0 <= _structure_score(answer) <= 1
    assert _example_score(answer) >= 0.6
    assert 0 <= _clarity_score(answer) <= 1


def test_grade_essay_heuristic_returns_breakdown_and_comment():
    result = grade_essay_heuristic(
        stem="Phân tích ưu nhược điểm của học có giám sát",
        answer_text="Đầu tiên nêu khái niệm. Sau đó ví dụ bài toán phân loại spam. Vì vậy có thể đánh giá bằng độ chính xác.",
        rubric=[
            {"criterion": "Đúng trọng tâm và chính xác", "points": 6},
            {"criterion": "Có ví dụ áp dụng", "points": 4},
        ],
        max_points=10,
        evidence_chunks=[{"text": "học có giám sát dùng dữ liệu có nhãn"}],
    )
    assert 0 <= result["score_points"] <= 10
    assert result["rubric_breakdown"]
    assert isinstance(result["comment"], str) and result["comment"]
