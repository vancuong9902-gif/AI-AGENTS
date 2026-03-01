import { useEffect, useMemo, useState } from "react";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";

function exportCsv(rows) {
  const header = ["student_id", "student_name", "placement_score", "final_score", "improvement", "homework_completion_rate", "tutor_sessions_count", "needs_support"];
  const lines = [header.join(",")];
  for (const r of rows) {
    lines.push(header.map((k) => JSON.stringify(r?.[k] ?? "")).join(","));
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "teacher_analytics.csv";
  a.click();
}

export default function TeacherAnalyticsDashboard() {
  const { role } = useAuth();
  const [classroomId, setClassroomId] = useState(localStorage.getItem("teacher_report_classroom_id") || "1");
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sortDesc, setSortDesc] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const data = await apiJson(`/lms/teacher/report/${Number(classroomId)}`);
      setReport(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (role === "teacher") load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role]);

  const rows = useMemo(() => {
    const arr = [...(report?.per_student || [])];
    arr.sort((a, b) => (sortDesc ? (Number(b.improvement || -999) - Number(a.improvement || -999)) : (Number(a.improvement || -999) - Number(b.improvement || -999))));
    return arr;
  }, [report, sortDesc]);

  return (
    <div style={{ padding: 16 }}>
      <h2>Teacher Analytics Dashboard</h2>
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <input value={classroomId} onChange={(e) => setClassroomId(e.target.value)} />
        <button onClick={load} disabled={loading}>{loading ? "Loading..." : "Load"}</button>
        <button onClick={() => setSortDesc((v) => !v)}>Sort improvement: {sortDesc ? "desc" : "asc"}</button>
        <button onClick={() => exportCsv(rows)}>Export CSV</button>
      </div>

      <div style={{ marginBottom: 12 }}><b>AI narrative:</b> {report?.ai_class_narrative || "—"}</div>

      <div style={{ marginBottom: 12 }}>
        <h4>Placement vs Final (bar-like)</h4>
        {(rows || []).map((s) => (
          <div key={s.student_id} style={{ marginBottom: 6 }}>
            <div>{s.student_name}</div>
            <div style={{ display: "flex", gap: 8 }}>
              <div style={{ background: "#dbeafe", width: `${Math.max(0, Number(s.placement_score || 0)) * 2}px`, height: 10 }} title={`placement ${s.placement_score ?? 0}`} />
              <div style={{ background: "#86efac", width: `${Math.max(0, Number(s.final_score || 0)) * 2}px`, height: 10 }} title={`final ${s.final_score ?? 0}`} />
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginBottom: 12 }}>
        <h4>Topic heatmap</h4>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(200px,1fr))", gap: 8 }}>
          {Object.entries(report?.topic_heatmap || {}).map(([topic, v]) => {
            const score = Number(v?.avg_score || 0);
            const color = score >= 75 ? "#dcfce7" : score >= 50 ? "#fef9c3" : "#fee2e2";
            return <div key={topic} style={{ background: color, border: "1px solid #e5e7eb", borderRadius: 8, padding: 8 }}><b>{topic}</b><div>{score}%</div></div>;
          })}
        </div>
      </div>

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead><tr><th>Tên</th><th>Placement</th><th>Final</th><th>Improvement</th><th>HW %</th><th>Tutor</th><th>Badge</th></tr></thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.student_id} style={{ borderTop: "1px solid #eee" }}>
              <td>{s.student_name}</td><td>{s.placement_score ?? "—"}</td><td>{s.final_score ?? "—"}</td><td>{s.improvement ?? "—"}</td><td>{s.homework_completion_rate ?? 0}</td><td>{s.tutor_sessions_count ?? 0}</td>
              <td>{s.needs_support ? <span style={{ background: "#fee2e2", padding: "2px 8px", borderRadius: 999 }}>Cần hỗ trợ</span> : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
