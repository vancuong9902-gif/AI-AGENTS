from app.services.exam_exporters import pdf_exporter as s


def test_wrap_text_handles_empty_and_long_text():
    assert s._wrap_text("", 10) == []
    wrapped = s._wrap_text("mot hai ba bon nam sau bay", 5)
    assert len(wrapped) >= 2
