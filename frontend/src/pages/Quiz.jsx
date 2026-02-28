import { useNavigate } from "react-router-dom";

export default function Quiz() {
  const nav = useNavigate();

  return (
    <div style={{ maxWidth: 820, margin: "0 auto", padding: 16 }}>
      <div style={{ border: "1px solid #eee", borderRadius: 14, padding: 16, background: "#fff" }}>
        <h2 style={{ marginTop: 0 }}>🧩 Luyện quiz</h2>
        <p style={{ margin: "8px 0", color: "#555", lineHeight: 1.6 }}>
          Giao diện <strong>Quiz</strong> đã được giản lược để học sinh chỉ cần bấm ở phần <strong>Bài tập về nhà</strong> trong Learning Path.
          <br />
          Bạn hãy vào Learning Path để làm trắc nghiệm + tự luận và nhận điểm ngay.
        </p>
        <button onClick={() => nav("/learning-path")}>Đi tới Learning Path</button>
      </div>
    </div>
  );
}
