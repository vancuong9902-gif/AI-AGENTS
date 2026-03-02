# Student Progress Analytics Design

This design is based on current backend tables in this repo:
- `attempts` (scores + duration)
- `quiz_sets` (topic metadata)
- `learning_plan_task_completions` (task completion)
- `learning_plan_homework_submissions` (homework grading)
- `sessions` (learning time)

## 1) SQL queries

> Notes:
> - Queries below are written for PostgreSQL.
> - Use `:student_id`, `:from_ts`, `:to_ts` as bind params.

### 1.1 Completion rate

Definition: completed tasks / total assigned tasks in learning plans.

```sql
WITH plan_scope AS (
  SELECT id
  FROM learning_plans
  WHERE user_id = :student_id
    AND created_at BETWEEN :from_ts AND :to_ts
),
tasks AS (
  SELECT
    COUNT(*) AS total_tasks,
    COUNT(*) FILTER (WHERE completed = TRUE) AS completed_tasks
  FROM learning_plan_task_completions c
  JOIN plan_scope p ON p.id = c.plan_id
)
SELECT
  total_tasks,
  completed_tasks,
  ROUND(100.0 * completed_tasks / NULLIF(total_tasks, 0), 2) AS completion_rate_pct
FROM tasks;
```

### 1.2 Average score

Definition: mean `attempts.score_percent` over the selected window.

```sql
SELECT
  COUNT(*) AS total_attempts,
  ROUND(AVG(a.score_percent)::numeric, 2) AS average_score_pct
FROM attempts a
WHERE a.user_id = :student_id
  AND a.created_at BETWEEN :from_ts AND :to_ts;
```

### 1.3 Improvement trend

Definition: daily average score and slope estimate between first and last day.

```sql
WITH daily AS (
  SELECT
    DATE(a.created_at) AS day,
    AVG(a.score_percent)::numeric(5,2) AS avg_score
  FROM attempts a
  WHERE a.user_id = :student_id
    AND a.created_at BETWEEN :from_ts AND :to_ts
  GROUP BY DATE(a.created_at)
),
ranked AS (
  SELECT
    day,
    avg_score,
    FIRST_VALUE(avg_score) OVER (ORDER BY day) AS first_score,
    FIRST_VALUE(avg_score) OVER (ORDER BY day DESC) AS last_score,
    FIRST_VALUE(day) OVER (ORDER BY day) AS first_day,
    FIRST_VALUE(day) OVER (ORDER BY day DESC) AS last_day
  FROM daily
)
SELECT DISTINCT
  first_score,
  last_score,
  ROUND(
    (last_score - first_score)
    / NULLIF((last_day - first_day), 0),
    4
  ) AS score_change_per_day,
  CASE
    WHEN last_score > first_score THEN 'up'
    WHEN last_score < first_score THEN 'down'
    ELSE 'flat'
  END AS trend_direction
FROM ranked;
```

### 1.4 Topic mastery %

Definition: weighted mastery by topic using attempt score and homework grade.

```sql
WITH attempt_topic AS (
  SELECT
    qs.topic,
    AVG(a.score_percent) AS quiz_avg
  FROM attempts a
  JOIN quiz_sets qs ON qs.id = a.quiz_set_id
  WHERE a.user_id = :student_id
    AND a.created_at BETWEEN :from_ts AND :to_ts
  GROUP BY qs.topic
),
homework_topic AS (
  SELECT
    lp.assigned_topic AS topic,
    AVG(COALESCE((h.grade_json ->> 'score_percent')::numeric, 0)) AS hw_avg
  FROM learning_plan_homework_submissions h
  JOIN learning_plans lp ON lp.id = h.plan_id
  WHERE h.user_id = :student_id
    AND h.created_at BETWEEN :from_ts AND :to_ts
    AND lp.assigned_topic IS NOT NULL
  GROUP BY lp.assigned_topic
)
SELECT
  COALESCE(a.topic, h.topic) AS topic,
  ROUND(COALESCE(a.quiz_avg, 0)::numeric, 2) AS quiz_avg_pct,
  ROUND(COALESCE(h.hw_avg, 0)::numeric, 2) AS homework_avg_pct,
  ROUND(
    (0.7 * COALESCE(a.quiz_avg, 0) + 0.3 * COALESCE(h.hw_avg, 0))::numeric,
    2
  ) AS topic_mastery_pct
FROM attempt_topic a
FULL OUTER JOIN homework_topic h ON h.topic = a.topic
ORDER BY topic_mastery_pct DESC NULLS LAST;
```

### 1.5 Time spent per topic

Preferred approach: log `topic` into `sessions.answers_snapshot_json` (or a dedicated `session_topic_events` table). Query below assumes `answers_snapshot_json` includes `{"topic": "..."}`.

```sql
WITH session_durations AS (
  SELECT
    s.id,
    s.user_id,
    GREATEST(
      0,
      EXTRACT(EPOCH FROM (COALESCE(s.ended_at, s.last_heartbeat_at, NOW()) - s.started_at))
    ) / 60.0 AS minutes,
    NULLIF((s.answers_snapshot_json -> 0 ->> 'topic'), '') AS topic
  FROM sessions s
  WHERE s.user_id = :student_id
    AND s.started_at BETWEEN :from_ts AND :to_ts
)
SELECT
  COALESCE(topic, 'unknown') AS topic,
  ROUND(SUM(minutes)::numeric, 2) AS total_minutes,
  ROUND(AVG(minutes)::numeric, 2) AS avg_minutes_per_session,
  COUNT(*) AS sessions
FROM session_durations
GROUP BY COALESCE(topic, 'unknown')
ORDER BY total_minutes DESC;
```

## 2) Backend API design

Base path: `/api/analytics/student-progress`

### 2.1 Summary endpoint

- `GET /api/analytics/student-progress/summary`
- Query params:
  - `student_id` (required)
  - `from` / `to` (optional, ISO-8601; default last 30 days)
  - `classroom_id` (optional, for teacher views)
- Response:

```json
{
  "student_id": 123,
  "window": {"from": "2026-01-01", "to": "2026-01-31"},
  "completion_rate_pct": 74.5,
  "average_score_pct": 81.2,
  "improvement": {
    "direction": "up",
    "score_change_per_day": 0.45
  },
  "topic_mastery_overall_pct": 78.9,
  "total_learning_minutes": 640
}
```

### 2.2 Topic breakdown endpoint

- `GET /api/analytics/student-progress/topics`
- Query params:
  - `student_id` (required)
  - `from` / `to` (optional)
  - `page` (default `1`), `page_size` (default `20`, max `100`)
  - `sort_by` (`mastery|time|score`, default `mastery`)
  - `order` (`asc|desc`, default `desc`)
- Response includes pagination:

```json
{
  "items": [
    {
      "topic": "Linear Algebra",
      "mastery_pct": 84.1,
      "avg_score_pct": 82.4,
      "time_spent_minutes": 120.5,
      "attempts": 6
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_items": 42,
    "total_pages": 3
  }
}
```

### 2.3 Trend endpoint

- `GET /api/analytics/student-progress/trend`
- Query params:
  - `student_id` (required)
  - `from` / `to` (optional)
  - `bucket` (`day|week`, default `day`)
- Response:

```json
{
  "points": [
    {
      "date": "2026-01-01",
      "avg_score_pct": 75,
      "completion_rate_pct": 50,
      "time_spent_minutes": 45
    }
  ]
}
```

### 2.4 Backend implementation notes

- Add service layer `analytics_student_progress_service.py` to keep SQL/business logic out of router.
- Add caching (Redis) for expensive trend queries, key by `(student_id, from, to, bucket)` with TTL 5-15 min.
- Authorization:
  - student can query self;
  - teacher/admin can query students in owned classroom.
- Error behavior in production: return user-safe messages (no stack trace leakage).

## 3) Frontend chart suggestions

1. **Completion rate**: radial progress or KPI card with delta vs previous window.
2. **Average score**: KPI card + sparkline (last 7/30 buckets).
3. **Improvement trend**: line chart (x=time, y=avg score) with trendline.
4. **Topic mastery %**: horizontal bar chart sorted descending (supports pagination/virtualization).
5. **Time spent per topic**: stacked bar (topic vs time) or treemap for quick proportional view.

Recommended dashboard layout:
- Top row: 4 KPI cards (completion, avg score, trend arrow, total time).
- Middle: score/completion trend chart.
- Bottom: two side-by-side charts (topic mastery + time per topic table/chart).
- States: loading skeleton, empty state ("No activity in selected window"), and retryable error banner.
