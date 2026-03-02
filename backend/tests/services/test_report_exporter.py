from app.services import report_exporter as s


def test_make_export_path_contains_extension():
    out = s.make_export_path(classroom_id=1, extension="pdf")
    assert out.endswith(".pdf")


def test_build_level_chart_returns_buffer():
    buf = s._build_level_chart({"gioi": 1})
    assert buf.read(4)
