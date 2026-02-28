# Tuning chia topic “thật chi tiết”

Các biến môi trường trong `backend/.env` ảnh hưởng mạnh tới mức độ chi tiết:

- `TOPIC_MAX_TOPICS` (mặc định v2: 120)  
  Tăng nếu tài liệu dài và bạn muốn nhiều topic hơn.

- `TOPIC_NUM_HEADING_MAX_DEPTH` (mặc định v2: 3)  
  Cho phép heading dạng số sâu hơn:
  - depth=2: 2.3 (không tách 2.3.1)
  - depth=3: 2.3.1 (chi tiết hơn)

- `TOPIC_MIN_BODY_CHARS` (mặc định v2: 1400)  
  Giảm để giữ các topic nhỏ; tăng để hệ thống tự *merge* topic nhỏ nhằm đảm bảo đủ dữ kiện sinh câu hỏi.

Gợi ý cấu hình theo mục tiêu:

## A) Ưu tiên “cực chi tiết để học”
```
TOPIC_NUM_HEADING_MAX_DEPTH=3
TOPIC_MIN_BODY_CHARS=900
TOPIC_MAX_TOPICS=180
```

## B) Cân bằng (khuyến nghị)
```
TOPIC_NUM_HEADING_MAX_DEPTH=3
TOPIC_MIN_BODY_CHARS=1400
TOPIC_MAX_TOPICS=120
```

## C) Ưu tiên ít topic nhưng chắc dữ kiện để ra đề
```
TOPIC_NUM_HEADING_MAX_DEPTH=2
TOPIC_MIN_BODY_CHARS=2200
TOPIC_MAX_TOPICS=60
```

Lưu ý:
- Quiz generation có cơ chế **auto-augment** context theo chunk-range của topic để vẫn ra đủ câu hỏi 3 độ khó.
