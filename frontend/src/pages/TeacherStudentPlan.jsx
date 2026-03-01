import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { API_BASE, apiJson } from "../lib/api";

function ScorePill({ score, max }) {
  const s = Number.isFinite(score) ? score : 0;
  const m = Number.isFinite(max) && max > 0 ? max : 0;
  const pct = m > 0 ? Math.round((s / m) * 100) : 0;
  return <span style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "6px 10px", borderRadius: 999, border: "1px solid #ddd", background: "#fafafa", fontSize: 13 }}><strong>{s}/{m}đ</strong><span style={{ color: "#666" }}>({pct}%)</span></span>;
}

export default function TeacherStudentPlan() {
  const { studentId } = useParams();
  const [sp] = useSearchParams();
  const classroomId = sp.get("classroom_id") || "";
  const [activeTab, setActiveTab] = useState("plan");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [aiEvaluation, setAiEvaluation] = useState(null);

  const plan = data?.plan || null;
  const days = useMemo(() => ((plan?.days || []).slice().sort((a, b) => Number(a.day_index) - Number(b.day_index))), [plan]);
  const submissions = data?.homework_submissions || {};



  const downloadStudentPdf = async () => {
    if (!classroomId) {
      setError("Thiếu classroom_id để xuất PDF học viên");
      return;
    }
    try {
      const headers = { "Cache-Control": "no-cache" };
      const uid = localStorage.getItem("user_id");
      const role = localStorage.getItem("role");
      if (uid) headers["X-User-Id"] = uid;
      if (role) headers["X-User-Role"] = role;
      const url = `${API_BASE}/lms/teacher/report/${Number(classroomId)}/student/${Number(studentId)}/export?format=pdf`;
      const res = await fetch(url, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `student_${Number(studentId)}_report.pdf`;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (e) {
      setError(`Tải PDF học viên thất bại: ${e?.message || e}`);
    }
  };

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const q = classroomId ? `?classroom_id=${encodeURIComponent(classroomId)}` : "";
        const resp = await apiJson(`/learning-plans/${studentId}/latest${q}`);
        setData(resp || null);
        if (classroomId) {
          const report = await apiJson(`/v1/lms/teacher/report/${Number(classroomId)}`);
          const student = (report?.students || []).find((s) => Number(s.user_id) === Number(studentId));
          setAiEvaluation(student?.ai_evaluation || null);
        }
      } catch (e) {
        setError(String(e?.message || e));
      } finally {
        setLoading(false);
      }
    })();
  }, [studentId, classroomId]);

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", padding: 16 }}>
      <h2 style={{ margin: 0 }}>👩‍🏫 Learning Path của học sinh</h2>
      <div style={{ color: "#666", marginTop: 4 }}>Student ID: <strong>{studentId}</strong>{classroomId ? <> • Classroom ID: <strong>{classroomId}</strong></> : null}</div>
      <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap" }}>
        {classroomId ? <Link to={`/teacher/classrooms/${classroomId}`} style={{ textDecoration: "none" }}>← Quay lại lớp</Link> : <Link to="/teacher/classrooms" style={{ textDecoration: "none" }}>← Quay lại danh sách lớp</Link>}
        {classroomId ? <button onClick={downloadStudentPdf} style={{ border: "1px solid #ddd", borderRadius: 8, padding: "6px 12px", background: "#111", color: "#fff", fontWeight: 700 }}>PDF học viên</button> : null}

      </div>

      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <button onClick={() => setActiveTab("plan")} style={{ background: activeTab === "plan" ? "#dbeafe" : "#fff" }}>Lộ trình học</button>
        <button onClick={() => setActiveTab("ai")} style={{ background: activeTab === "ai" ? "#dbeafe" : "#fff" }}>Đánh giá AI</button>
      </div>

      {error && <div style={{ marginTop: 12, padding: 10, border: "1px solid #ffa39e", background: "#fff1f0", borderRadius: 10 }}>{error}</div>}
      {loading && <div style={{ color: "#666", marginTop: 10 }}>Đang tải…</div>}

      {activeTab === "ai" ? (
        <div style={{ marginTop: 12, border: "1px solid #eee", borderRadius: 14, padding: 16, background: "#fff" }}>
          {!aiEvaluation ? <div style={{ color: "#666" }}>Chưa có đánh giá AI cho học sinh này.</div> : (
            <div style={{ display: "grid", gap: 10 }}>
              <div><strong>Tóm tắt:</strong> {aiEvaluation.summary || "—"}</div>
              <div><strong>Điểm mạnh:</strong> {(aiEvaluation.strengths || []).join(", ") || "—"}</div>
              <div><strong>Cần cải thiện:</strong> {(aiEvaluation.improvements || []).join(", ") || "—"}</div>
              <div><strong>Khuyến nghị:</strong> {aiEvaluation.recommendation || "—"}</div>
            </div>
          )}
        </div>
      ) : (
        <>
          {!plan ? <div style={{ border: "1px solid #eee", borderRadius: 14, padding: 16, background: "#fff", color: "#666", marginTop: 12 }}>Học sinh chưa có Learning Plan được lưu.</div> : (
            <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
              {(days || []).map((d) => {
                const sub = submissions?.[d.day_index] || null;
                const grade = sub?.grade || null;
                const score = Number(grade?.score_points || 0);
                const max = Number(grade?.max_points || 0);
                const hasSub = !!sub;
                return (
                  <details key={d.day_index} style={{ border: "1px solid #eee", borderRadius: 14, padding: 12, background: "#fff" }}>
                    <summary style={{ cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                      <div style={{ fontWeight: 900 }}>Bài {d.day_index}: {d.title}{!hasSub && <span style={{ marginLeft: 10, color: "#999", fontWeight: 600 }}>(chưa nộp)</span>}</div>
                      {hasSub && <ScorePill score={score} max={max} />}
                    </summary>
                    {grade?.comment ? <div style={{ marginTop: 10 }}><strong>Nhận xét:</strong> {grade.comment}</div> : null}
                  </details>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
