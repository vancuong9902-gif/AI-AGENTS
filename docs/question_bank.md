# Question Bank Generator (Teacher)

Endpoint: `POST /api/documents/{document_id}/question-bank/generate`

Mục tiêu:
- Tự động tạo *ngân hàng câu hỏi* theo từng topic của tài liệu
- Mỗi topic sinh tối thiểu `question_count_per_level` câu cho mỗi độ khó trong `levels`

## Request body
```json
{
  "user_id": 1,
  "levels": ["beginner","intermediate","advanced"],
  "question_count_per_level": 10,
  "topic_ids": null,
  "rag_top_k": 6
}
```

## Demo headers (bắt buộc teacher)
- `X-User-Id: 1`
- `X-User-Role: teacher`

## Response
Trả về danh sách `{topic_id, topic, level, quiz_id, question_count}`.
