from app.services import topic_service


def test_analyze_semantic_content_returns_requested_schema(monkeypatch):
    monkeypatch.setattr(
        topic_service,
        "extract_topics",
        lambda _text, include_details=True, max_topics=12: {
            "topics": [
                {
                    "title": "Hàm số bậc hai",
                    "subtopics": ["Đỉnh parabol", "Trục đối xứng"],
                    "key_points": ["Xác định đỉnh", "Vẽ đồ thị"],
                    "summary": "Nắm các đặc trưng chính của hàm số bậc hai.",
                    "content_len": 1400,
                    "definitions": [{"term": "Parabol", "meaning": "..."}],
                }
            ]
        },
    )

    out = topic_service.analyze_semantic_content("raw text", max_topics=8)

    assert isinstance(out, dict)
    assert "topics" in out and isinstance(out["topics"], list)
    assert len(out["topics"]) == 1

    topic = out["topics"][0]
    assert topic["title"] == "Hàm số bậc hai"
    assert topic["subtopics"] == ["Đỉnh parabol", "Trục đối xứng"]
    assert topic["objectives"] == ["Xác định đỉnh", "Vẽ đồ thị"]
    assert 1 <= int(topic["difficulty"]) <= 5
    assert int(topic["estimated_time_minutes"]) > 0


def test_analyze_semantic_content_empty_text():
    out = topic_service.analyze_semantic_content("")
    assert out == {"topics": []}
