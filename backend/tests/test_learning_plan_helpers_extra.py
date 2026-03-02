from app.services import learning_plan_service as lps


def test_level_and_difficulty_sequence_defaults():
    assert lps._level_from_score(90) == "gioi"
    assert lps._level_from_score(55) == "trung_binh"
    seq = lps._pick_difficulty_sequence(5, {"hard": 0, "medium": 0, "easy": 0})
    assert len(seq) == 5
    assert set(seq).issubset({"easy", "medium", "hard"})


def test_generate_learning_plan_items_for_weak_level_contains_tutor_item():
    plan = lps.generate_learning_plan_items(
        user_id=1,
        classroom_id=2,
        level="yeu",
        weak_topics=[{"id": 5, "title": "Phân số"}],
        all_topics=[{"id": 6, "title": "Số thập phân"}],
    )
    assert plan["student_level"] == "yeu"
    assert plan["total_items"] == len(plan["items"])
    assert any(item["content_ref"] == "tutor_ai:foundation_boost" for item in plan["items"])


def test_mode_cap_compact_and_title_tokens():
    assert lps._mode("no") == "off"
    assert lps._cap_int("abc", default=5, lo=1, hi=9) == 5
    assert lps._compact("  xin   chao  ") == "xin chao"
    assert lps._title_tokens("Giới thiệu về Hệ quản trị cơ sở dữ liệu", max_tokens=3)


def test_sanitize_rubric_builds_fallback_and_normalizes_points():
    rb = lps._sanitize_rubric([], max_points=10)
    assert rb and sum(x["points"] for x in rb) == 10
    rb2 = lps._sanitize_rubric([
        {"criterion": "Tiêu chí 1", "points": 9},
        {"criterion": "Tiêu chí 2", "points": 9},
    ], max_points=10)
    assert sum(x["points"] for x in rb2) == 10


def test_offline_homework_contains_source_and_points_bounds():
    hw = lps._offline_homework("Xác suất", level="beginner", max_points=99, sources=[12])
    assert hw.max_points <= 30
    assert hw.sources == [{"chunk_id": 12}]
    assert "Xác suất" in hw.stem
