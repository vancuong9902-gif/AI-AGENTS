import { useEffect, useMemo, useState } from "react";
import { apiJson, API_BASE } from "../lib/api";
import { useAuth } from "../context/AuthContext";

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
  const queryCid = new URLSearchParams(window.location.search).get("classroomId");
  const [classroomId, setClassroomId] = useState(queryCid || localStorage.getItem("teacher_report_classroom_id") || "1");
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState("overview");
  const [keyword, setKeyword] = useState("");
  const [sortBy, setSortBy] = useState("improvement");
  const [selected, setSelected] = useState(null);
  const [sortDesc, setSortDesc] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      localStorage.setItem("teacher_report_classroom_id", String(cid));
      const res = await apiJson(`/v1/lms/teacher/report/${cid}`);
      setReport(res?.data || res);
      const data = await apiJson(`/lms/teacher/report/${Number(classroomId)}`);
      setReport(data);
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
