from app.services import topic_service


def test_generate_topic_map_from_extracted_text_shape_and_333(monkeypatch):
    def _fake_extract_topics(_text, include_details=False, max_topics=24):
        return {
            "topics": [
                {"title": "Phương trình bậc hai", "summary": "Nội dung về phương trình", "body": "Định nghĩa. Công thức nghiệm. Ví dụ áp dụng."},
                {"title": "Bài tập", "summary": "Không phải topic", "body": "Câu 1"},
            ]
        }

    monkeypatch.setattr(topic_service, "extract_topics", _fake_extract_topics)

    out = topic_service.generate_topic_map_from_extracted_text(
        document_title="Toán 10",
        extracted_text="Chương 1...",
        toc_hints=["Mục lục"],
    )
    assert isinstance(out, dict)
    topics = out.get("topics")
    assert isinstance(topics, list)
    assert len(topics) == 1

    topic = topics[0]
    assert topic["title"] == "Phương trình bậc hai"
    assert "practice_pack" in topic
    for level in ("easy", "medium", "hard"):
        assert len(topic["practice_pack"][level]) == 3
        stems = [q["stem"] for q in topic["practice_pack"][level]]
        assert len(stems) == len(set(stems))


def test_generate_topic_map_empty_input():
    out = topic_service.generate_topic_map_from_extracted_text(document_title="", extracted_text="")
    assert out == {"topics": []}
