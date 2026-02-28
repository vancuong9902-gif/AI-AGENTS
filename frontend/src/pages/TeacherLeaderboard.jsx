import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiJson } from "../lib/api";

export default function TeacherLeaderboard() {
  const { id } = useParams();
  const assessmentId = Number(id);

  const [meta, setMeta] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await apiJson(`/teacher/assessments/${assessmentId}/leaderboard`, { method: "GET" });
      setMeta(data || null);
      setRows(Array.isArray(data?.leaderboard) ? data.leaderboard : []);
    } catch (e) {
      setError(e?.message || "Không load được leaderboard");
      setRows([]);
      setMeta(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (Number.isFinite(assessmentId)) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assessmentId]);

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0 }}>🏆 Leaderboard — Assessment {assessmentId}</h2>
          <div style={{ color: "#666", marginTop: 4 }}>{meta?.title ? `Tiêu đề: ${meta.title}` : ""}</div>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <Link to="/teacher/assessments" style={{ textDecoration: "none" }}>
            <button style={{ padding: "8px 12px" }}>⬅ Quản lý</button>
          </Link>
          <button onClick={load} disabled={loading} style={{ padding: "8px 12px" }}>
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div style={{ marginTop: 12, background: "#fff3f3", border: "1px solid #ffd0d0", padding: 12, borderRadius: 12 }}>
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ color: "#666", marginTop: 12 }}>Đang tải…</div>
      ) : (
        <div style={{ marginTop: 12, background: "#fff", borderRadius: 12, padding: 12, boxShadow: "0 2px 10px rgba(0,0,0,0.06)" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #eee" }}>
                <th style={{ padding: 8 }}>#</th>
                <th style={{ padding: 8 }}>Student ID</th>
                <th style={{ padding: 8 }}>Score %</th>
                <th style={{ padding: 8 }}>Status</th>
                <th style={{ padding: 8 }}>Submitted at</th>
                <th style={{ padding: 8 }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, idx) => (
                <tr key={`${r.student_id}-${r.attempt_id}`} style={{ borderBottom: "1px solid #f3f3f3" }}>
                  <td style={{ padding: 8 }}>{idx + 1}</td>
                  <td style={{ padding: 8 }}>{r.student_id}</td>
                  <td style={{ padding: 8 }}>{r.score_percent}</td>
                  <td style={{ padding: 8 }}>{r.status || "-"}</td>
                  <td style={{ padding: 8, color: "#666" }}>{r.created_at}</td>
                  <td style={{ padding: 8 }}>
                    <Link to={`/teacher/assessments/${assessmentId}/grade/${r.student_id}`} style={{ textDecoration: "none" }}>
                      <button style={{ padding: "6px 10px" }}>Chấm / Xem bài</button>
                    </Link>
                  </td>
                </tr>
              ))}

              {rows.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ padding: 12, color: "#666" }}>
                    Chưa có học sinh nộp bài.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ marginTop: 12, color: "#666" }}>
        Demo so sánh: mở tab Student với các ID khác nhau (1,2,3) → làm bài → quay lại đây xem thứ hạng.
      </div>
    </div>
  );
}
