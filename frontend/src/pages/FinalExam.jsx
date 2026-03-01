import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/useAuth";

export default function FinalExam() {
  const navigate = useNavigate();
  const { userId } = useAuth();

  const classroomId = Number(localStorage.getItem("active_classroom_id") || 0);
  const [assessments, setAssessments] = useState([]);
  const [progress, setProgress] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const latestFinal = useMemo(() => {
    return [...assessments]
      .filter((a) => String(a?.kind || "").toLowerCase() === "diagnostic_post")
      .sort((a, b) => new Date(b?.created_at || 0).getTime() - new Date(a?.created_at || 0).getTime())[0];
  }, [assessments]);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      if (!classroomId) {
        setAssessments([]);
        setProgress(null);
        return;
      }
      const [assessmentRows, progressRow] = await Promise.all([
        apiJson(`/assessments?classroom_id=${classroomId}`),
        apiJson(`/lms/student/${Number(userId || 0)}/progress?classroom_id=${classroomId}`),
      ]);
      setAssessments(Array.isArray(assessmentRows) ? assessmentRows : []);
      setProgress(progressRow || null);
    } catch (e) {
      setError(e?.message || "Không tải được thông tin cuối kỳ.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classroomId, userId]);

  const delta = Number(progress?.delta ?? 0);

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", padding: 16 }}>
      <div style={{ background: "linear-gradient(120deg, #312e81 0%, #2563eb 100%)", color: "white", borderRadius: 16, padding: 20, boxShadow: "0 12px 28px rgba(37,99,235,0.35)" }}>
        <div style={{ fontSize: 28, fontWeight: 900, letterSpacing: 0.3 }}>🎓 BÀI KIỂM TRA CUỐI KỲ</div>
        <div style={{ opacity: 0.9, marginTop: 6 }}>Đây là bài đánh giá cuối kỳ, khác với bài kiểm tra đầu vào (diagnostic_pre).</div>
      </div>

      {!classroomId && (
        <div style={{ marginTop: 12, padding: 12, borderRadius: 12, border: "1px solid #fecaca", background: "#fff1f2", color: "#9f1239" }}>
          Chưa có lớp học đang hoạt động. Hãy vào danh sách lớp và chọn lớp trước khi làm bài cuối kỳ.
        </div>
      )}

      {error ? <div style={{ marginTop: 12, color: "#b42318" }}>{error}</div> : null}
      {loading ? <div style={{ marginTop: 12, color: "#6b7280" }}>Đang tải dữ liệu cuối kỳ…</div> : null}

      {!loading && (
        <>
          <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
            <div style={{ background: "#eef2ff", border: "1px solid #c7d2fe", borderRadius: 12, padding: 12 }}>
              <div style={{ color: "#4338ca", fontSize: 12 }}>Điểm đầu vào</div>
              <div style={{ fontSize: 26, fontWeight: 800 }}>{progress?.pre_score != null ? `${Number(progress.pre_score).toFixed(1)}%` : "--"}</div>
            </div>
            <div style={{ background: "#eff6ff", border: "1px solid #93c5fd", borderRadius: 12, padding: 12 }}>
              <div style={{ color: "#1d4ed8", fontSize: 12 }}>Điểm cuối kỳ</div>
              <div style={{ fontSize: 26, fontWeight: 800 }}>{progress?.post_score != null ? `${Number(progress.post_score).toFixed(1)}%` : "--"}</div>
            </div>
            <div style={{ background: "#f5f3ff", border: "1px solid #c4b5fd", borderRadius: 12, padding: 12 }}>
              <div style={{ color: "#6d28d9", fontSize: 12 }}>Chênh lệch</div>
              <div style={{ fontSize: 26, fontWeight: 800, color: delta >= 0 ? "#166534" : "#b91c1c" }}>
                {progress?.delta != null ? `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}%` : "--"}
              </div>
            </div>
          </div>

          <div style={{ marginTop: 12, background: "white", border: "1px solid #e5e7eb", borderRadius: 12, padding: 16 }}>
            <div style={{ fontWeight: 800, marginBottom: 4 }}>Bài cuối kỳ hiện tại</div>
            {latestFinal ? (
              <>
                <div>{latestFinal.title}</div>
                <div style={{ color: "#6b7280", fontSize: 14, marginTop: 4 }}>
                  Tạo lúc: {latestFinal.created_at || "--"} • Cấp độ: {latestFinal.level || "--"}
                </div>
                <button
                  style={{ marginTop: 12, padding: "10px 14px", borderRadius: 10, border: "none", background: "#4f46e5", color: "white", fontWeight: 700 }}
                  onClick={() => navigate(`/assessments/${latestFinal.assessment_id}?mode=final`, { state: { examMode: "final" } })}
                >
                  Bắt đầu thi
                </button>
              </>
            ) : (
              <div style={{ color: "#6b7280" }}>Chưa có bài cuối kỳ (diagnostic_post) cho lớp này.</div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
