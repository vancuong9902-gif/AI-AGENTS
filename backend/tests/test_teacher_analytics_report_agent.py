from app.services.teacher_analytics_report_agent import build_teacher_analytics_report


def test_build_teacher_analytics_report_shape_and_values():
    payload = build_teacher_analytics_report(
        class_roster=[
            {"student_id": 1, "student_name": "An"},
            {"student_id": 2, "student_name": "Binh"},
        ],
        attempts=[
            {
                "student_id": 1,
                "score": 80,
                "submitted_at": "2026-01-02T10:00:00",
                "breakdown": [{"topic": "Algebra", "percent": 70}],
            },
            {
                "student_id": 2,
                "score": 60,
                "submitted_at": "2026-01-02T12:00:00",
                "breakdown": [{"topic": "Geometry", "percent": 50}],
            },
        ],
        learning_time_logs=[
            {"student_id": 1, "hours": 1.5},
            {"student_id": 1, "hours": 2.0},
            {"student_id": 2, "hours": 1.0},
        ],
        pre_vs_post=[
            {"student_id": 1, "pre_score": 65, "post_score": 80, "topic_scores": {"Algebra": 60, "Geometry": 64}},
            {"student_id": 2, "pre_score": 55, "post_score": 60, "topic_scores": {"Geometry": 50}},
        ],
    )

    assert payload["status"] == "OK"
    summary = payload["report"]["summary"]
    assert summary["class_size"] == 2
    assert summary["average_score"] == 70.0
    assert summary["average_progress"] == 10.0
    assert summary["top_weak_topics"][0] == "Geometry"

    charts = payload["report"]["charts"]
    assert charts["scores_over_time"] == [{"date": "2026-01-02", "avg_score": 70.0}]
    assert len(charts["topic_mastery_heatmap"]) == 2

    gradebook = payload["report"]["export_payloads"]["excel_gradebook"]
    assert "columns" in gradebook and "rows" in gradebook
    assert len(gradebook["rows"]) == 2
