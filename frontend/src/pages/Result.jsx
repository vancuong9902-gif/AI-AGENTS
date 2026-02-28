import { Link } from "react-router-dom";

export default function Result() {
  return (
    <div style={{ maxWidth: 820, margin: "0 auto", padding: 16 }}>
      <div style={{ border: "1px solid #eee", borderRadius: 14, padding: 16, background: "#fff" }}>
        <h2 style={{ marginTop: 0 }}>📊 Kết quả</h2>
        <p style={{ margin: "8px 0", color: "#555", lineHeight: 1.6 }}>
          Trang <strong>Kết quả Quiz</strong> đã được đơn giản hoá.
          <br />
          Hiện tại, phần trắc nghiệm + tự luận và điểm số được hiển thị trực tiếp trong <strong>Learning Path → Bài tập về nhà</strong>.
        </p>
        <Link to="/learning-path">Đi tới Learning Path</Link>
      </div>
    </div>
  );
}
