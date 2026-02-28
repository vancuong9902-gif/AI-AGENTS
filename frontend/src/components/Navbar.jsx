import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Navbar() {
  const { role, userId } = useAuth();

  return (
    <nav style={{ display: "flex", gap: 16, alignItems: "center", padding: 12, borderBottom: "1px solid #eee" }}>
      <Link to="/">Login</Link>
      <span style={{ color: "#666" }}>ID: {userId ?? 1}</span>

      {role === "student" && (
        <>
          <Link to="/classrooms">🏫 Lớp học</Link>
          <Link to="/assessments">📝 Bài tổng hợp</Link>
          <Link to="/learning-path">📌 Learning Path</Link>
          <Link to="/tutor">🤖 Tutor (Hỏi đáp)</Link>
          <Link to="/analytics">📊 Analytics</Link>
        </>
      )}

      {role === "teacher" && (
        <>
          <Link to="/teacher/classrooms">🏫 Lớp học</Link>
          <Link to="/upload">📤 Upload</Link>
          <Link to="/teacher/assessments">👩‍🏫 Quản lý bài tổng hợp</Link>
          <Link to="/teacher/progress">📈 Progress Dashboard</Link>
          <Link to="/teacher/analytics">📊 Analytics Dashboard</Link>
          <Link to="/teacher/infra">⚙️ Infra (Jobs/Drift)</Link>
          <Link to="/teacher/files">📚 Thư viện file</Link>
        </>
      )}
      <Link to="/health">Health</Link>
    </nav>
  );
}
