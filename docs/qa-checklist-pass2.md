# QA Checklist — PASS 2 (Polish)

## 1) UI consistency
- [x] Chuẩn hóa nhãn trên sidebar/topbar theo tiếng Việt.
- [x] Đồng bộ trạng thái nút và thông điệp trên trang Upload (tải lên, tiến độ, trạng thái xử lý).
- [x] Cải thiện bố cục topbar trên mobile để không vỡ hàng.

## 2) Tiếng Việt
- [x] Thống nhất thuật ngữ `chủ đề` thay cho `topic/topics` ở các nhãn người dùng.
- [x] Rút gọn một số câu thông báo để ngắn gọn, dễ hiểu.
- [x] Sửa chính tả/dấu câu cho các nhãn hành động (`Xóa`, `Tải PDF lên`, `Tiến độ`).

## 3) Accessibility (A11y)
- [x] Bổ sung `aria-label` cho vùng kéo-thả và input chọn tệp PDF.
- [x] Bổ sung `aria-label` cho các input chỉnh sửa chủ đề động.
- [x] Bổ sung `aria-expanded`, `aria-controls`, `aria-haspopup` cho nút mở menu và chuông thông báo.
- [x] Hỗ trợ đóng drawer/notification bằng phím `Escape`.

## 4) Responsive
- [x] Khoá cuộn nền khi mobile drawer mở.
- [x] Tối ưu topbar actions trên màn hình nhỏ.
- [x] Tinh chỉnh vị trí dropdown thông báo trên mobile.

## 5) Lint / Build / hygiene
- [x] Không thêm TODO mới.
- [ ] `npm run lint` chưa chạy được do thiếu gói cài đặt trong môi trường hiện tại.
- [ ] `npm run build` chưa chạy được do chưa có `vite` binary trong môi trường hiện tại.

## File thay đổi chính
- `frontend/src/App.jsx`
- `frontend/src/App.css`
- `frontend/src/components/Navbar.jsx`
- `frontend/src/components/NotificationBell.jsx`
- `frontend/src/pages/Upload.jsx`
- `docs/qa-checklist-pass2.md`
