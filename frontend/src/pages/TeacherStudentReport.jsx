import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer, BarChart, CartesianGrid, XAxis, YAxis, Tooltip, Bar } from "recharts";
import { apiJson } from "../lib/api";

function pct(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, Math.round(n * 100) / 100));
}

export default function TeacherStudentReport() {
  const { studentId } = useParams();
  const sid = Number(studentId);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reports, setReports] = useState([]);

  useEffect(() => {
    let mounted = true;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const data = await apiJson(`/teacher/reports/${sid}`);
        if (!mounted) return;
        setReports(Array.isArray(data?.reports) ? data.reports : []);
      } catch (e) {
        if (!mounted) return;
        setError(e?.message || "Không tải được báo cáo");
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [sid]);

  const latest = reports[0] || null;
  const payload = latest?.payload || {};
  const analytics = payload?.analytics || {};

  const topicData = useMemo(() => {
    const byTopic = analytics?.by_topic || {};
    return Object.entries(byTopic).map(([k, v]) => ({ topic: k, score: pct(v?.percent) }));
  }, [analytics]);

  const difficultyData = useMemo(() => {
    const byDifficulty = analytics?.by_difficulty || {};
    const labels = [
      ["easy", "Dễ"],
      ["medium", "Trung bình"],
      ["hard", "Khó"],
    ];
    return labels.map(([k, label]) => ({ name: label, score: pct(byDifficulty?.[k]?.percent) }));
  }, [analytics]);

  const studentName = latest?.student?.name || `Học sinh #${sid}`;

  return (
    <div style={{ maxWidth: 1080, margin: "0 auto", padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div>
          <h2 style={{ margin: 0 }}>📘 Báo cáo cuối kỳ: {studentName}</h2>
          <div style={{ color: "#666" }}>Student ID: {sid}</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Link to="/teacher/classrooms" style={{ textDecoration: "none" }}>
            <button style={{ padding: "8px 12px" }}>⬅ Danh sách lớp</button>
          </Link>
          <button onClick={() => window.print()} style={{ padding: "8px 12px" }}>Xuất PDF</button>
        </div>
      </div>

      {loading ? <div>Đang tải…</div> : null}
      {error ? <div style={{ background: "#fff3f3", border: "1px solid #ffd0d0", padding: 12, borderRadius: 12 }}>{error}</div> : null}
      {!loading && !error && !latest ? <div style={{ color: "#666" }}>Chưa có báo cáo cuối kỳ.</div> : null}

      {latest ? (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div style={{ background: "#fff", borderRadius: 12, padding: 12, boxShadow: "0 2px 10px rgba(0,0,0,0.06)", minHeight: 320 }}>
              <div style={{ fontWeight: 700, marginBottom: 8 }}>Radar chart theo topic</div>
              <ResponsiveContainer width="100%" height={260}>
                <RadarChart data={topicData}>
                  <PolarGrid />
                  <PolarAngleAxis dataKey="topic" />
                  <PolarRadiusAxis angle={30} domain={[0, 100]} />
                  <Radar name="Điểm" dataKey="score" stroke="#2563eb" fill="#60a5fa" fillOpacity={0.6} />
                </RadarChart>
              </ResponsiveContainer>
            </div>

            <div style={{ background: "#fff", borderRadius: 12, padding: 12, boxShadow: "0 2px 10px rgba(0,0,0,0.06)", minHeight: 320 }}>
              <div style={{ fontWeight: 700, marginBottom: 8 }}>Bar chart theo độ khó</div>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={difficultyData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis domain={[0, 100]} />
                  <Tooltip />
                  <Bar dataKey="score" fill="#10b981" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div style={{ marginTop: 12, background: "#fff", borderRadius: 12, padding: 12, boxShadow: "0 2px 10px rgba(0,0,0,0.06)" }}>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>🤖 AI nhận xét</div>
            <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{latest.message}</div>
          </div>
        </>
      ) : null}
    </div>
  );
}
