from __future__ import annotations

from app.services.bloom import BLOOM_LEVELS, allocate_bloom_counts, get_level_distribution, infer_bloom_level, normalize_bloom_level


def test_bloom_helpers_coverage():
    assert len(BLOOM_LEVELS) > 0
    distribution = get_level_distribution("beginner")
    allocated = allocate_bloom_counts(total=10, distribution=distribution)
    assert isinstance(allocated, dict)
    assert sum(allocated.values()) == 10
    assert isinstance(get_level_distribution("unknown"), dict)
    assert infer_bloom_level("analyze and compare") in BLOOM_LEVELS
    assert normalize_bloom_level("REMEMBER") in BLOOM_LEVELS
