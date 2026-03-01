from app.services.topic_service import _is_bad_heading_candidate


def test_rejects_table_of_contents_heading_as_topic():
    assert _is_bad_heading_candidate("Mục lục") is True
    assert _is_bad_heading_candidate("Table of Contents") is True


def test_rejects_answer_appendix_heading_as_topic():
    assert _is_bad_heading_candidate("Phụ lục đáp án") is True
