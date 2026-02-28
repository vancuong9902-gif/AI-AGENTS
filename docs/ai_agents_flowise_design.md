# AI Learning Agents — Thiết kế hệ thống (Flowise + Backend)

## 1) Mục tiêu
Xây dựng hệ AI Agents cho học tập theo luồng:
- Giảng viên upload tài liệu → hệ thống chia topic chi tiết → sinh ngân hàng câu hỏi 3 độ khó
- Sinh viên làm test đầu vào → chấm điểm → phân tích năng lực → cá nhân hoá lộ trình → luyện tập → test cuối khoá
- Hệ thống tự đánh giá tiến độ, tự điều chỉnh độ khó, tổng hợp báo cáo.

## 2) Thành phần
- **Frontend**: React/Vite (demo)
- **Backend**: FastAPI + Postgres + RAG/Quiz/Topics/Learning Plan (đã có trong repo)
- **Flowise**: Orchestrator cho multi-agent (AgentFlow V2) + Tools gọi API backend

## 3) Agents (đặc tả ngắn)
1. **Ingestion Agent**: upload & chunk tài liệu, (tuỳ chọn) embeddings.
2. **Topic Builder Agent**: chia topic thật chi tiết; không dùng mục "Bài tập/Đáp án" làm topic độc lập.
3. **Question Bank Agent**: mỗi topic → sinh tối thiểu 10 câu / độ khó (Beginner, Intermediate, Advanced) + đáp án + giải thích + nguồn.
4. **Diagnostic Agent**: tạo test đầu vào phủ topic chính (hoặc adaptive).
5. **Grader Agent**: chấm + giải thích; lưu attempt; cập nhật mastery.
6. **Student Modeling Agent**: cập nhật hồ sơ năng lực theo topic.
7. **Learning Path Planner Agent**: dựng lộ trình theo mastery + prerequisites.
8. **Tutor Agent**: chat giải thích + tạo bài luyện tập bám tài liệu.
9. **Progress Evaluator Agent**: theo dõi tiến độ, auto tăng/giảm độ khó.
10. **Report Agent**: báo cáo cho giảng viên/sinh viên.

## 4) Guardrails (để không bịa)
- Sinh câu hỏi/giải thích **phải bám context** (RAG) và ưu tiên trích `chunk_id`.
- Nếu context lỗi OCR → trả lỗi NEED_CLEAN_TEXT (backend đã có cơ chế).
- Không lấy “đáp án” có sẵn trong tài liệu làm dữ kiện cho câu hỏi (lọc practice/answer key).

## 5) Mapping theo sơ đồ swimlane
Xem hình: `docs/images/ai-agent-swimlane.png`

- Teacher: Đăng nhập → Upload → Tạo test đầu vào/ngân hàng câu hỏi
- Student: Làm test → Nộp → Học theo lộ trình → Làm bài tập/quiz → Test cuối
- System: Sinh câu hỏi → Chấm → Phân tích năng lực → Xếp mức → Cá nhân hoá → Đánh giá tiến độ → Tổng hợp

## 6) Flowise integration (tóm tắt)
Xem: `flowise/blueprints/agentflow_v2_orchestrator_blueprint.md`

