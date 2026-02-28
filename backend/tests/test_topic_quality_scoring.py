from app.services.topic_service import extract_topics


def test_extract_topics_filters_undermentioned_topics_and_adds_quality_fields():
    full_text = """
    Chương 1: Phương trình bậc hai
    Phương trình bậc hai có dạng ax^2 + bx + c = 0.

    Chương 2: Ma trận nâng cao
    Nội dung ma trận nâng cao giới thiệu ngắn.
    """

    chunks = [
        "Phương trình bậc hai có công thức nghiệm và biệt thức delta.",
        "Trong bài học phương trình bậc hai, học sinh luyện áp dụng công thức nghiệm.",
        "Ứng dụng phương trình bậc hai trong bài toán thực tế và đồ thị hàm số.",
        "Ma trận nâng cao chỉ được nhắc sơ lược trong tài liệu này.",
    ]

    obj = extract_topics(
        full_text,
        chunks_texts=chunks,
        heading_level="chapter",
        include_details=False,
        max_topics=10,
    )

    assert obj.get("status") == "OK"
    topics = obj.get("topics") or []
    assert len(topics) == 1

    topic = topics[0]
    assert topic.get("title")
    assert 0.0 <= float(topic.get("coverage_score", 0.0)) <= 1.0
    assert topic.get("confidence") in {"high", "medium", "low"}
    assert isinstance(topic.get("sample_content"), str) and topic.get("sample_content")
    assert isinstance(topic.get("subtopics"), list)
    assert isinstance(topic.get("page_ranges"), list)
