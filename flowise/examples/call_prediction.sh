#!/usr/bin/env bash
set -euo pipefail

FLOWISE_URL="${FLOWISE_URL:-http://localhost:3000}"
FLOW_ID="${FLOW_ID:-YOUR_FLOW_ID}"

curl -sS -X POST "$FLOWISE_URL/api/v1/prediction/$FLOW_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "form": {
      "role": "student",
      "action": "tutor_chat",
      "classroom_id": 1,
      "teacher_id": 1,
      "student_id": 2,
      "document_ids": [1],
      "selected_topics": ["Biến và kiểu dữ liệu"],
      "question": "Giải thích sự khác nhau giữa biến và hằng số, kèm ví dụ.",
      "difficulty_config": {"easy": 4, "medium": 4, "hard": 2},
      "duration_seconds": 1800,
      "exclude_history": []
    }
  }' | jq .
