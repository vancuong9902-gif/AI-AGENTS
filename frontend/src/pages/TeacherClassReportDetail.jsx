import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiJson, API_BASE } from "../lib/api";

function downloadTextFile(name, text, type = "text/plain") {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export default function TeacherClassReportDetail() {
  const { id, reportId } = useParams();
  const navigate = useNavigate();
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    const run = async () => {
      setLoading(true);
      setError("");
      try {
        const data = await apiJson(`/classrooms/${Number(id)}/reports/${Number(reportId)}`);
        if (mounted) setReport(data);
      } catch (e) {
        if (mounted) setError(e?.message || "Không tải được báo cáo lớp");
      } finally {
        if (mounted) setLoading(false);
      }
    };
    run();
    return () => {
      mounted = false;
    };
  }, [id, reportId]);

  const levelData = useMemo(() => {
    const d = report?.stats?.level_distribution || {};
    return [
      { label: "Yếu", value: Number(d.yeu || 0), color: "#ef4444" },
      { label: "TB", value: Number(d.trung_binh || 0), color: "#f59e0b" },
      { label: "Khá", value: Number(d.kha || 0), color: "#3b82f6" },
      { label: "Giỏi", value: Number(d.gioi || 0), color: "#22c55e" },
    ];
  }, [report]);

  const students = Array.isArray(report?.improvement?.students) ? report.improvement.students : [];
  const weakTopics = Array.isArray(report?.stats?.weak_topics) ? report.stats.weak_topics.slice(0, 3) : [];

  const exportPdf = () => {
    const content = [
      "BÁO CÁO TỔNG KẾT CUỐI KỲ",
      `Lớp: ${id}`,
      `Report ID: ${reportId}`,
      `Ngày tạo: ${report?.created_at || ""}`,
      "",
      "Narrative:",
      report?.narrative || "",
    ].join("\n");
    downloadTextFile(`class_report_${reportId}.pdf.txt`, content, "text/plain;charset=utf-8");
  };

  const exportExcel = () => {
    window.open(`${API_BASE}/classrooms/${Number(id)}/reports/${Number(reportId)}/export/excel`, "_blank");
  };

  return (
    <div style={{ maxWidth: 1120, margin: "0 auto", padding: 16 }}>
      <button onClick={() => navigate(-1)} style={{ marginBottom: 12 }}>← Quay lại</button>
      <h2 style={{ marginTop: 0 }}>📊 Report Detail (Classroom #{id})</h2>

      {loading ? <div>Đang tải…</div> : null}
      {error ? <div style={{ color: "#b91c1c" }}>{error}</div> : null}

      {!loading && report ? (
        <>
          <div style={{ background: "#fff", borderRadius: 14, padding: 14, marginBottom: 12 }}>
            <h3>Narrative AI</h3>
            <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{report.narrative || "(trống)"}</p>
            <div style={{ display: "flex", gap: 10 }}>
              <button onClick={exportPdf}>Xuất PDF</button>
              <button onClick={exportExcel}>Xuất Excel</button>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div style={{ background: "#fff", borderRadius: 14, padding: 14 }}>
              <h3>So sánh điểm đầu vào vs cuối kỳ</h3>
              <div style={{ display: "grid", gap: 6 }}>
                {students.map((s) => (
                  <div key={s.student_id} style={{ display: "grid", gridTemplateColumns: "80px 1fr", alignItems: "center", gap: 8 }}>
                    <div>HS {s.student_id}</div>
                    <div style={{ background: "#e5e7eb", borderRadius: 10, overflow: "hidden", position: "relative", height: 20 }}>
                      <div style={{ width: `${Number(s.entry_score || 0)}%`, background: "#93c5fd", height: 8 }} />
                      <div style={{ width: `${Number(s.final_score || 0)}%`, background: "#2563eb", height: 12 }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ background: "#fff", borderRadius: 14, padding: 14 }}>
              <h3>Phân bổ Yếu/TB/Khá/Giỏi</h3>
              {levelData.map((x) => (
                <div key={x.label} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <div style={{ width: 12, height: 12, borderRadius: 999, background: x.color }} />
                  <div style={{ minWidth: 60 }}>{x.label}</div>
                  <div style={{ fontWeight: 700 }}>{x.value}</div>
                </div>
              ))}
            </div>
          </div>

          <div style={{ background: "#fff", borderRadius: 14, padding: 14, marginTop: 12 }}>
            <h3>Top 3 topic yếu + gợi ý dạy lại</h3>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left" }}>Topic</th>
                  <th style={{ textAlign: "left" }}>Avg</th>
                  <th style={{ textAlign: "left" }}>Gợi ý</th>
                </tr>
              </thead>
              <tbody>
                {weakTopics.map((w) => (
                  <tr key={w.topic}>
                    <td>{w.topic}</td>
                    <td>{w.avg_pct}%</td>
                    <td>{w.suggestion}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </div>
  );
}
