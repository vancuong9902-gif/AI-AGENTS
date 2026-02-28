#!/usr/bin/env bash
set -euo pipefail

FLOWISE_URL="${FLOWISE_URL:-http://localhost:3000}"
FLOW_ID="${FLOW_ID:-YOUR_FLOW_ID}"

curl -sS -X POST "$FLOWISE_URL/api/v1/prediction/$FLOW_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "form": {
      "action": "tutor_chat",
      "user_id": 2,
      "document_id": 1,
      "topic": "Biến và kiểu dữ liệu",
      "question": "Giải thích sự khác nhau giữa biến và hằng số, kèm ví dụ."
    }
  }' | jq .
