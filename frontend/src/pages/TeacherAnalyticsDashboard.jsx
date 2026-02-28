import { Fragment, useEffect, useMemo, useState } from "react";
import { apiJson, API_BASE } from "../lib/api";
import { useAuth } from "../context/AuthContext";

function levelBadge(level) {
  const label = level?.label || "N/A";
  const tone = label === "Giỏi" ? "#dcfce7" : label === "Khá" ? "#dbeafe" : label === "Trung bình" ? "#fef3c7" : "#fee2e2";
  return <span style={{ padding: "4px 8px", borderRadius: 999, background: tone }}>{label}</span>;
}

export default function TeacherAnalyticsDashboard() {
  const { role } = useAuth();
  const [classroomId, setClassroomId] = useState(localStorage.getItem("teacher_report_classroom_id") || "1");
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [expandedId, setExpandedId] = useState(null);

  const loadReport = async () => {
    const cid = Number(classroomId);
    if (!Number.isFinite(cid) || cid <= 0) return;
    setLoading(true);
    setError("");
    try {
      localStorage.setItem("teacher_report_classroom_id", String(cid));
      const data = await apiJson(`/v1/lms/teacher/report/${cid}`);
      setReport(data);
    } catch (e) {
      setError(e?.message || "Không thể tải báo cáo lớp.");
      setReport(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (role === "teacher") loadReport();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role]);

  const overview = useMemo(() => {
    const students = report?.students || [];
    const withFinal = students.filter((s) => Number.isFinite(Number(s.final_score)));
    const avg = withFinal.length ? withFinal.reduce((acc, s) => acc + Number(s.final_score), 0) / withFinal.length : 0;
    const impVals = students.filter((s) => Number.isFinite(Number(s.improvement))).map((s) => Number(s.improvement));
    const avgImp = impVals.length ? impVals.reduce((acc, v) => acc + v, 0) / impVals.length : 0;
    const top = students.filter((s) => (s.level?.key || "") === "gioi").length;
    return { total: students.length, avg, avgImp, top };
  }, [report]);

  const exportReport = async (format) => {
    const cid = Number(classroomId);
    const url = `${API_BASE}/v1/lms/teacher/report/${cid}/export?format=${format}`;
    const res = await fetch(url, { headers: { "X-User-Id": localStorage.getItem("user_id") || "1", "X-User-Role": localStorage.getItem("role") || "teacher" } });
    if (!res.ok) throw new Error(`Export failed (${res.status})`);
    const contentType = res.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const json = await res.json();
      const blob = new Blob([JSON.stringify(json, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `teacher_report_${cid}.json`;
      a.click();
      return;
    }
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `teacher_report_${cid}.html`;
    a.click();
  };

  if (role !== "teacher") return <div style={{ padding: 16 }}>Trang này dành cho giáo viên.</div>;

  return (
    <div style={{ maxWidth: 1180, margin: "0 auto", padding: 16 }}>
      <h2>📊 Teacher Analytics Dashboard</h2>
      <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
        <input value={classroomId} onChange={(e) => setClassroomId(e.target.value)} style={{ padding: 8, borderRadius: 8, border: "1px solid #ddd", width: 140 }} />
        <button onClick={loadReport} disabled={loading}>{loading ? "Đang tải..." : "Tải báo cáo"}</button>
      </div>

      {error ? <div style={{ background: "#fff1f2", border: "1px solid #fecdd3", borderRadius: 10, padding: 10 }}>{error}</div> : null}

      {report ? (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 14 }}>
            <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 12, padding: 12 }}><div style={{ fontSize: 24, fontWeight: 800 }}>{overview.total} HS</div><div>Tổng học sinh</div></div>
            <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 12, padding: 12 }}><div style={{ fontSize: 24, fontWeight: 800 }}>{overview.avg.toFixed(1)}%</div><div>Điểm TB</div></div>
            <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 12, padding: 12 }}><div style={{ fontSize: 24, fontWeight: 800 }}>{overview.avgImp >= 0 ? "+" : ""}{overview.avgImp.toFixed(1)}%</div><div>Cải thiện TB</div></div>
            <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 12, padding: 12 }}><div style={{ fontSize: 24, fontWeight: 800 }}>{overview.top}</div><div>Top HS (Giỏi)</div></div>
          </div>

          <div style={{ overflowX: "auto", background: "#fff", border: "1px solid #eee", borderRadius: 12, padding: 10 }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid #eee" }}>
                  <th>Tên</th><th>Đầu vào</th><th>Cuối kỳ</th><th>+/-</th><th>Level</th><th>AI Note</th>
                </tr>
              </thead>
              <tbody>
                {(report.students || []).map((s) => (
                  <Fragment key={s.user_id}>
                    <tr key={s.user_id} onClick={() => setExpandedId(expandedId === s.user_id ? null : s.user_id)} style={{ borderBottom: "1px solid #f3f4f6", cursor: "pointer" }}>
                      <td>{s.name}</td>
                      <td>{s.diagnostic_score ?? "N/A"}%</td>
                      <td>{s.final_score ?? "N/A"}%</td>
                      <td>{s.improvement ?? "N/A"}</td>
                      <td>{levelBadge(s.level)}</td>
                      <td>{s.ai_evaluation?.summary || "—"}</td>
                    </tr>
                    {expandedId === s.user_id ? (
                      <tr>
                        <td colSpan={6} style={{ background: "#fafafa", padding: 10 }}>
                          <div><strong>Strengths:</strong> {(s.ai_evaluation?.strengths || []).join(", ") || "—"}</div>
                          <div><strong>Improvements:</strong> {(s.ai_evaluation?.improvements || []).join(", ") || "—"}</div>
                          <div><strong>Recommendation:</strong> {s.ai_evaluation?.recommendation || "—"}</div>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ marginTop: 14, background: "#eef2ff", border: "1px solid #c7d2fe", borderRadius: 12, padding: 12 }}>
            <strong>🤖 AI nhận xét lớp học:</strong> {report.class_summary?.overall_assessment || "Chưa có nhận xét"}
          </div>

          <div style={{ marginTop: 14, display: "flex", gap: 10 }}>
            <button onClick={() => exportReport("html")}>📄 Xuất báo cáo HTML</button>
            <button onClick={() => exportReport("json")}>📊 Xuất JSON</button>
          </div>
        </>
      ) : null}
    </div>
  );
}
