from app.services import rag_service as s


def test_score_for_single_word_hit_and_miss():
    assert s._score("python", "hoc python") == 1.0
    assert s._score("python", "java") == 0.0


def test_clean_filter_list_removes_nullish():
    assert s._clean_filter_list(["a", None, " null ", "b"]) == ["a", "b"]
