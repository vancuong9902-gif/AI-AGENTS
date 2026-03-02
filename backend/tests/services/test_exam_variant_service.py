from app.services import exam_variant_service as s


def test_jaccard_handles_empty_sets():
    assert s._jaccard(set(), set()) == 0.0


def test_stem_signature_normalizes_strings():
    sig = s._stem_signature([{"stem": "  Câu A? "}, {"stem": "câu a?"}])
    assert len(sig) == 1
