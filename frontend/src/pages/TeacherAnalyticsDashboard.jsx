import { useEffect, useMemo, useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from "recharts";
import { apiJson, API_BASE, buildAuthHeaders } from "../lib/api";
import { useAuth } from "../context/AuthContext";

export default function TeacherAnalyticsDashboard() {
  const { role, userId } = useAuth();
  const [classroomId, setClassroomId] = useState(localStorage.getItem("teacher_report_classroom_id") || "1");
  const [report, setReport] = useState(null);
  const [hoursData, setHoursData] = useState([]);
  const [loading, setLoading] = useState(false);

  const loadReport = async () => {
    const cid = Number(classroomId || 0);
    if (!cid) return;
    setLoading(true);
    try {
      localStorage.setItem("teacher_report_classroom_id", String(cid));
      const data = await apiJson(`/lms/teacher/report/${cid}`);
      setReport(data);
      if (userId) {
        const hours = await apiJson(`/analytics/learning-hours?user_id=${Number(userId)}&days=30`);
        setHoursData(Array.isArray(hours) ? hours : []);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (role === "teacher") loadReport();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role]);

  const rows = useMemo(() => Array.isArray(report?.per_student) ? report.per_student : [], [report]);

  const download = async (url, filename) => {
    const res = await fetch(url, { headers: buildAuthHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  if (role !== "teacher") return <div style={{ padding: 16 }}>Trang này dành cho giáo viên.</div>;

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: 16 }}>
      <h2>📊 Teacher Analytics Dashboard</h2>
      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        <input value={classroomId} onChange={(e) => setClassroomId(e.target.value)} style={{ width: 120 }} />
        <button onClick={loadReport}>{loading ? "Đang tải..." : "Tải báo cáo"}</button>
        <button onClick={() => download(`${API_BASE}/lms/teacher/report/${Number(classroomId)}/export/pdf`, `teacher_report_${classroomId}.pdf`)}>📄 Xuất Báo Cáo PDF</button>
        <button onClick={() => download(`${API_BASE}/lms/teacher/report/${Number(classroomId)}/export/excel`, `teacher_report_${classroomId}.xlsx`)}>📊 Xuất Excel</button>
      </div>

      <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 10, padding: 12, marginBottom: 12 }}>
        <div>Tổng HS: <b>{report?.summary?.total_students || 0}</b></div>
        <div>Đã có final: <b>{report?.summary?.students_with_final || 0}</b></div>
      </div>

      <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 10, padding: 12, marginBottom: 12 }}>
        <h3 style={{ marginTop: 0 }}>Biểu đồ giờ học theo ngày (30 ngày)</h3>
        <div style={{ width: "100%", height: 280 }}>
          <ResponsiveContainer>
            <LineChart data={hoursData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="hours" stroke="#2563eb" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead><tr><th>Tên</th><th>Placement</th><th>Final</th><th>Improvement</th></tr></thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.student_id} style={{ borderTop: "1px solid #eee" }}>
              <td>{s.student_name || s.name}</td><td>{s.placement_score ?? "—"}</td><td>{s.final_score ?? "—"}</td><td>{s.improvement ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
