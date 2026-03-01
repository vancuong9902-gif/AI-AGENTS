import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import { API_BASE, apiJson, buildAuthHeaders } from "../lib/api";

const LEVEL_LABEL = {
  gioi: "Giỏi",
  kha: "Khá",
  trung_binh: "Trung bình",
  yeu: "Yếu",
};

const LEVEL_COLORS = {
  gioi: "#22c55e",
  kha: "#3b82f6",
  trung_binh: "#f59e0b",
  yeu: "#ef4444",
};

function Card({ children }) {
  return <div style={{ background: "#fff", borderRadius: 12, padding: 16, boxShadow: "0 2px 12px rgba(0,0,0,0.08)" }}>{children}</div>;
}

function SummaryCard({ title, value, hint }) {
  return (
    <Card>
      <div style={{ color: "#666", fontSize: 12, fontWeight: 700 }}>{title}</div>
      <div style={{ fontSize: 28, fontWeight: 800, marginTop: 6 }}>{value}</div>
      {hint ? <div style={{ marginTop: 4, color: "#666", fontSize: 13 }}>{hint}</div> : null}
    </Card>
  );
}

export default function TeacherClassroomDashboard() {
  const { id } = useParams();
  const classroomId = Number(id);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [levelFilter, setLevelFilter] = useState("all");
  const [sortBy, setSortBy] = useState("final_desc");

  useEffect(() => {
    if (!Number.isFinite(classroomId) || classroomId <= 0) return;
    (async () => {
      setLoading(true);
      setErr("");
      try {
        const data = await apiJson(`/lms/teacher/report/${classroomId}`);
        setReport(data);
      } catch (e) {
        setErr(e?.message || "Không thể tải báo cáo lớp học");
      } finally {
        setLoading(false);
      }
    })();
  }, [classroomId]);

  const students = useMemo(() => {
    const list = Array.isArray(report?.student_list) ? [...report.student_list] : [];
    const filtered = levelFilter === "all" ? list : list.filter((s) => s.level === levelFilter);
    const score = (v) => (typeof v === "number" ? v : -1);
    const sorter = {
      final_desc: (a, b) => score(b.final_score) - score(a.final_score),
      final_asc: (a, b) => score(a.final_score) - score(b.final_score),
      entry_desc: (a, b) => score(b.entry_score) - score(a.entry_score),
      improvement_desc: (a, b) => score(b.improvement) - score(a.improvement),
      name_asc: (a, b) => String(a.name || "").localeCompare(String(b.name || "")),
    };
    filtered.sort(sorter[sortBy] || sorter.final_desc);
    return filtered;
  }, [report, levelFilter, sortBy]);

  const pieData = useMemo(() => {
    const dist = report?.class_analytics?.score_distribution || {};
    return ["gioi", "kha", "trung_binh", "yeu"].map((key) => ({ name: LEVEL_LABEL[key], key, value: Number(dist[key]) || 0 }));
  }, [report]);

  const downloadFile = async (url, filename) => {
    const res = await fetch(url, { headers: buildAuthHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  const exportPdf = async () => {
    try {
      await downloadFile(`${API_BASE}/lms/teacher/report/${classroomId}/export?format=pdf`, `teacher-report-class-${classroomId}.pdf`);
    } catch (e) {
      setErr(`Xuất PDF thất bại: ${e?.message || e}`);
    }
  };


  const exportXlsx = async () => {
    try {
      await downloadFile(`${API_BASE}/lms/teacher/report/${classroomId}/export/excel`, `teacher-report-class-${classroomId}.xlsx`);
    } catch (e) {
      setErr(`Xuất Excel thất bại: ${e?.message || e}`);
    }
  };

  const generateVariants = async () => {
    try {
      const payload = {
        teacher_id: Number(localStorage.getItem("user_id") || 1),
        classroom_id: classroomId,
        title_prefix: "Mã đề",
        n_variants: 3,
        easy_count: 5,
        medium_count: 5,
        hard_count: 2,
        topics: [],
        document_ids: [],
      };
      const data = await apiJson(`/exams/generate-variants`, { method: "POST", body: JSON.stringify(payload) });
      const exportUrl = data?.data?.export_url;
      if (exportUrl) {
        await downloadFile(`${API_BASE}${exportUrl}`, `variants_class_${classroomId}.zip`);
      }
    } catch (e) {
      setErr(`Sinh mã đề thất bại: ${e?.message || e}`);
    }
  };

  const summary = report?.summary || {};
  const completionRate = summary.total_students > 0 ? Math.round((summary.completed_final_exam / summary.total_students) * 100) : 0;

  return (
    <div style={{ padding: 20, display: "grid", gap: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0 }}>Báo cáo giáo viên - Lớp #{classroomId}</h2>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={generateVariants} style={{ border: "1px solid #ddd", borderRadius: 8, padding: "10px 14px", background: "#f3f4f6", color: "#111", fontWeight: 700 }}>Sinh N mã đề</button>
          <button onClick={exportXlsx} style={{ border: "1px solid #ddd", borderRadius: 8, padding: "10px 14px", background: "#0f766e", color: "#fff", fontWeight: 700 }}>📥 Xuất Excel</button>
          <button onClick={exportPdf} style={{ border: "1px solid #ddd", borderRadius: 8, padding: "10px 14px", background: "#111", color: "#fff", fontWeight: 700 }}>Tải báo cáo PDF lớp</button>
        </div>
      </div>

      {loading ? <Card>Đang tải báo cáo...</Card> : null}
      {err ? <Card><div style={{ color: "#b91c1c" }}>{err}</div></Card> : null}

      {report ? (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
            <SummaryCard title="Tổng học sinh" value={summary.total_students || 0} />
            <SummaryCard title="Hoàn thành đầu vào" value={summary.completed_entry_test || 0} />
            <SummaryCard title="Hoàn thành cuối kỳ" value={`${summary.completed_final_exam || 0} (${completionRate}%)`} />
            <SummaryCard title="Điểm TB đầu vào" value={(summary.average_entry_score || 0).toFixed(1)} />
            <SummaryCard title="Điểm TB cuối kỳ" value={(summary.average_final_score || 0).toFixed(1)} hint={`Cải thiện TB: ${(summary.average_improvement || 0).toFixed(1)}`} />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1.2fr", gap: 12 }}>
            <Card>
              <h3 style={{ marginTop: 0 }}>Phân loại học sinh</h3>
              <div style={{ width: "100%", height: 280 }}>
                <ResponsiveContainer>
                  <PieChart>
                    <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={90} label>
                      {pieData.map((e) => <Cell key={e.key} fill={LEVEL_COLORS[e.key]} />)}
                    </Pie>
                    <Legend />
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </Card>

            <Card>
              <h3 style={{ marginTop: 0 }}>Tiến trình học theo thời gian</h3>
              <div style={{ width: "100%", height: 280 }}>
                <ResponsiveContainer>
                  <LineChart data={report?.class_analytics?.improvement_chart || []}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis domain={[0, 100]} />
                    <Tooltip />
                    <Line type="monotone" dataKey="avg_score" stroke="#2563eb" strokeWidth={3} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>

          <Card>
            <h3 style={{ marginTop: 0 }}>Danh sách học sinh</h3>
            <div style={{ display: "flex", gap: 10, marginBottom: 10 }}>
              <select value={levelFilter} onChange={(e) => setLevelFilter(e.target.value)}>
                <option value="all">Tất cả mức</option>
                <option value="gioi">Giỏi</option>
                <option value="kha">Khá</option>
                <option value="trung_binh">Trung bình</option>
                <option value="yeu">Yếu</option>
              </select>
              <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
                <option value="final_desc">Điểm cuối kỳ giảm dần</option>
                <option value="final_asc">Điểm cuối kỳ tăng dần</option>
                <option value="entry_desc">Điểm đầu vào giảm dần</option>
                <option value="improvement_desc">Tiến bộ giảm dần</option>
                <option value="name_asc">Tên A-Z</option>
              </select>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left", borderBottom: "1px solid #eee", padding: 8 }}>Học sinh</th>
                    <th style={{ textAlign: "left", borderBottom: "1px solid #eee", padding: 8 }}>Level</th>
                    <th style={{ textAlign: "right", borderBottom: "1px solid #eee", padding: 8 }}>Entry</th>
                    <th style={{ textAlign: "right", borderBottom: "1px solid #eee", padding: 8 }}>Final</th>
                    <th style={{ textAlign: "right", borderBottom: "1px solid #eee", padding: 8 }}>Improvement</th>
                    <th style={{ textAlign: "right", borderBottom: "1px solid #eee", padding: 8 }}>Homework %</th>
                  </tr>
                </thead>
                <tbody>
                  {students.map((s) => (
                    <tr key={s.student_id} style={{ background: s.level === "yeu" ? "#fee2e2" : "transparent" }}>
                      <td style={{ padding: 8 }}>{s.name}</td>
                      <td style={{ padding: 8 }}>{LEVEL_LABEL[s.level] || s.level}</td>
                      <td style={{ padding: 8, textAlign: "right" }}>{s.entry_score == null ? "-" : s.entry_score.toFixed(1)}</td>
                      <td style={{ padding: 8, textAlign: "right" }}>{s.final_score == null ? "-" : s.final_score.toFixed(1)}</td>
                      <td style={{ padding: 8, textAlign: "right" }}>{s.improvement == null ? "-" : s.improvement.toFixed(1)}</td>
                      <td style={{ padding: 8, textAlign: "right" }}>{(Number(s.homework_completion_rate) || 0).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card>
            <h3 style={{ marginTop: 0 }}>AI nhận xét tổng quát</h3>
            <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{report.ai_recommendations || "Chưa có nhận xét."}</div>
          </Card>
        </>
      ) : null}
    </div>
  );
}
