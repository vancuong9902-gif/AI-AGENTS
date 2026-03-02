from app.services import bloom as s


def test_allocate_bloom_counts_sum_matches_total():
    out = s.allocate_bloom_counts(7, {"remember": 1.0})
    assert sum(out.values()) == 7


def test_infer_bloom_level_defaults_and_detects():
    assert s.infer_bloom_level("") == "understand"
    assert s.infer_bloom_level("Hãy phân tích nguyên nhân") == "analyze"
