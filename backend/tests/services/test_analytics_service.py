from app.services import analytics_service as s


def test_compute_knowledge_from_topic_mastery():
    mj = {"topic_mastery": {"doc1:topic2": 0.8}}
    assert s.compute_knowledge(mj, document_id=1) == 0.8


def test_normalize_weights_handles_invalid_values():
    out = s._normalize_weights({"w1_knowledge": -3, "w2_improvement": 0})
    assert out["w1_knowledge"] > 0
