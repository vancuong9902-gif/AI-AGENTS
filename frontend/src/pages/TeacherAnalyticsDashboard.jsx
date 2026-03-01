import { useEffect, useMemo, useState } from "react";
import { apiJson, API_BASE } from "../lib/api";
import { useAuth } from "../context/AuthContext";

export default function TeacherAnalyticsDashboard() {
  const { role } = useAuth();
  const queryCid = new URLSearchParams(window.location.search).get("classroomId");
  const [classroomId, setClassroomId] = useState(queryCid || localStorage.getItem("teacher_report_classroom_id") || "1");
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState("overview");
  const [keyword, setKeyword] = useState("");
  const [sortBy, setSortBy] = useState("improvement");
  const [selected, setSelected] = useState(null);

  const loadReport = async () => {
    const cid = Number(classroomId);
    if (!Number.isFinite(cid) || cid <= 0) return;
    setLoading(true);
    try {
      localStorage.setItem("teacher_report_classroom_id", String(cid));
      const res = await apiJson(`/v1/lms/teacher/report/${cid}`);
      setReport(res?.data || res);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (role === "teacher") loadReport(); }, [role]);

  const rows = useMemo(() => {
    const arr = (report?.per_student || []).filter((s) => (s?.name || "").toLowerCase().includes(keyword.toLowerCase()));
    return [...arr].sort((a, b) => Number(b?.[sortBy] || -999) - Number(a?.[sortBy] || -999));
  }, [report, keyword, sortBy]);

  const exportCsv = () => {
    const headers = ["student_id", "name", "placement_score", "final_score", "improvement", "homework_completion_rate", "tutor_sessions_count", "weak_topics", "strong_topics", "ai_comment"];
    const lines = [headers.join(",")].concat((report?.per_student || []).map((r) => headers.map((h) => JSON.stringify(r?.[h] ?? "")).join(",")));
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `teacher_report_${classroomId}.csv`;
    a.click();
  };

  const exportHtml = async () => {
    const cid = Number(classroomId);
    const res = await fetch(`${API_BASE}/v1/lms/teacher/report/${cid}/export?format=html`, { headers: { "X-User-Id": localStorage.getItem("user_id") || "1", "X-User-Role": "teacher" } });
    const blob = await res.blob();
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `teacher_report_${cid}.html`; a.click();
  };

  if (role !== "teacher") return <div style={{ padding: 16 }}>Trang này dành cho giáo viên.</div>;

  return <div style={{ maxWidth: 1200, margin: "0 auto", padding: 16 }}>
    <h2>📊 Teacher Analytics Dashboard</h2>
    <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
      <input value={classroomId} onChange={(e) => setClassroomId(e.target.value)} style={{ width: 120 }} />
      <button onClick={loadReport}>{loading ? "Đang tải..." : "Tải báo cáo"}</button>
      <button onClick={exportCsv}>⬇️ CSV</button>
      <button onClick={exportHtml}>⬇️ HTML</button>
    </div>

    <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
      <button onClick={() => setTab("overview")}>Overview</button>
      <button onClick={() => setTab("students")}>Per Student</button>
      <button onClick={() => setTab("heatmap")}>Heatmap</button>
    </div>

    {tab === "overview" && <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 10, padding: 12 }}>
      <div>Tổng HS: <b>{report?.summary?.total_students || 0}</b></div>
      <div>Đã có final: <b>{report?.summary?.students_with_final || 0}</b></div>
      <div>Cải thiện TB: <b>{report?.summary?.avg_improvement || 0}%</b></div>
    </div>}

    {tab === "students" && <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 10, padding: 10 }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <input placeholder="Tìm học sinh" value={keyword} onChange={(e) => setKeyword(e.target.value)} />
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
          <option value="improvement">Improvement</option>
          <option value="final_score">Final score</option>
          <option value="homework_completion_rate">Homework completion</option>
        </select>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead><tr><th>Tên</th><th>Placement</th><th>Final</th><th>+/−</th><th>Homework</th><th>Tutor</th></tr></thead>
        <tbody>
          {rows.map((s) => <tr key={s.student_id} onClick={() => setSelected(s)} style={{ cursor: "pointer", borderTop: "1px solid #f1f5f9" }}>
            <td>{s.name}</td><td>{s.placement_score ?? "-"}</td><td>{s.final_score ?? "-"}</td><td>{s.improvement ?? "-"}</td><td>{s.homework_completion_rate}%</td><td>{s.tutor_sessions_count}</td>
          </tr>)}
        </tbody>
      </table>
    </div>}

    {tab === "heatmap" && <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 10 }}>
      {(report?.topic_heatmap || []).map((h) => {
        const v = Number(h.avg_score || 0);
        const bg = v >= 80 ? "#22c55e" : v >= 65 ? "#facc15" : "#ef4444";
        return <div key={h.topic} style={{ borderRadius: 8, padding: 12, color: "#111", background: `${bg}55` }}><div><b>{h.topic}</b></div><div>{v}%</div><div>{h.students} HS</div></div>;
      })}
    </div>}

    {selected && <div onClick={() => setSelected(null)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)", display: "grid", placeItems: "center" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, width: 560, maxWidth: "90vw", padding: 16 }}>
        <h3>{selected.name}</h3>
        <div>AI: {selected.ai_comment}</div>
        <div>Weak: {(selected.weak_topics || []).join(", ") || "-"}</div>
        <div>Strong: {(selected.strong_topics || []).join(", ") || "-"}</div>
        <button onClick={() => setSelected(null)}>Đóng</button>
      </div>
    </div>}
  </div>;
}
