import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";

const kindLabelMap = {
  diagnostic_pre: "Đầu vào",
  midterm: "Bài tổng hợp",
  diagnostic_post: "Cuối kỳ",
};

function fmtTime(sec) {
  if (sec == null) return "--:--";
  const total = Math.max(0, Number(sec) || 0);
  const mm = String(Math.floor(total / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

export default function AssessmentTake() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { userId } = useAuth();
  const assessmentId = Number(id);

  const [data, setData] = useState(null);
  const [attemptId, setAttemptId] = useState(null);
  const [answers, setAnswers] = useState({});
  const [timeLeftSec, setTimeLeftSec] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [progress, setProgress] = useState(null);
  const [toasts, setToasts] = useState([]);

  const warnedRef = useRef({ five: false, one: false });
  const autoSubmitRef = useRef(false);

  const examMode = location.state?.examMode || new URLSearchParams(location.search).get("mode");
  const classroomId = Number(localStorage.getItem("active_classroom_id") || 0);

  const questions = data?.questions || [];
  const answeredCount = useMemo(() => Object.keys(answers).length, [answers]);
  const isFinalExam = String(data?.kind || "").toLowerCase() === "diagnostic_post";

  const pushToast = (message) => {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts((prev) => [...prev, { id, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3000);
  };

  const loadProgress = async () => {
    if (!classroomId || !userId) return;
    try {
      const row = await apiJson(`/lms/student/${Number(userId)}/progress?classroom_id=${classroomId}`);
      setProgress(row || null);
    } catch {
      // optional panel only
    }
  };

  const load = async () => {
    if (!Number.isFinite(assessmentId)) return;
    setLoading(true);
    setError("");
    setResult(null);
    warnedRef.current = { five: false, one: false };
    autoSubmitRef.current = false;

    try {
      const assessment = await apiJson(`/assessments/${assessmentId}`);
      setData(assessment || null);
      const started = await apiJson("/attempts/start", {
        method: "POST",
        body: { quiz_id: Number(assessment?.assessment_id || assessmentId), student_id: Number(userId || 0) },
      });
      setAttemptId(Number(started?.attempt_id || 0) || null);
      const initialSec = Number(started?.remaining_seconds || assessment?.duration_seconds || 0);
      setTimeLeftSec(Number.isFinite(initialSec) && initialSec > 0 ? initialSec : null);
      if (String(assessment?.kind || "").toLowerCase() === "diagnostic_post") {
        loadProgress();
      }
    } catch (e) {
      setError(e?.message || "Không tải được bài kiểm tra.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assessmentId]);

  useEffect(() => {
    if (timeLeftSec == null || result || submitting) return;
    const t = setInterval(() => {
      setTimeLeftSec((prev) => (prev == null ? prev : Math.max(0, prev - 1)));
    }, 1000);
    return () => clearInterval(t);
  }, [timeLeftSec, result, submitting]);

  useEffect(() => {
    if (timeLeftSec == null || result || submitting) return;
    if (timeLeftSec <= 300 && !warnedRef.current.five) {
      warnedRef.current.five = true;
      pushToast("Còn 5 phút");
    }
    if (timeLeftSec <= 60 && !warnedRef.current.one) {
      warnedRef.current.one = true;
      pushToast("Còn 1 phút");
    }
    if (timeLeftSec <= 0 && !autoSubmitRef.current) {
      autoSubmitRef.current = true;
      submit(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeLeftSec, result, submitting]);

  const submit = async (auto = false) => {
    if (!attemptId || !data) return;
    setSubmitting(true);
    setError("");
    try {
      const answerList = questions.map((q) => ({
        question_id: q.question_id,
        answer_index: answers[q.question_id]?.answer_index ?? null,
        answer_text: answers[q.question_id]?.answer_text ?? null,
      }));
      const r = await apiJson(`/attempts/${attemptId}/submit`, {
        method: "POST",
        body: { answers: answerList, force: Boolean(auto) },
      });
      setResult(r);
      if (String(data?.kind || "").toLowerCase() === "diagnostic_post") {
        loadProgress();
      }
    } catch (e) {
      setError(e?.message || "Nộp bài thất bại.");
      setSubmitting(false);
      return;
    }
    setSubmitting(false);
  };

  if (loading) return <div style={{ padding: 16 }}>Đang tải bài kiểm tra…</div>;
  if (error && !data) return <div style={{ padding: 16, color: "#b42318" }}>{error}</div>;

  if (result) {
    const score = Number(result?.total_score_percent ?? result?.score_percent ?? 0);
    const delta = Number(progress?.delta ?? 0);

    return (
      <div style={{ maxWidth: 980, margin: "0 auto", padding: 16 }}>
        <h2>Kết quả bài kiểm tra</h2>
        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12, padding: 16 }}>
          <div>Điểm: <b>{Math.round(score)}/100</b></div>
          <div>Đúng: {Number(result?.correct_count || 0)} / {Number(result?.total_questions || questions.length)}</div>
          <div>Thời gian làm bài: {fmtTime(Number(result?.time_spent_seconds || 0))}</div>
        </div>

        {isFinalExam && (
          <div style={{ marginTop: 12, background: "#f5f3ff", border: "1px solid #c4b5fd", borderRadius: 12, padding: 16 }}>
            <h3 style={{ marginTop: 0, color: "#5b21b6" }}>So sánh đầu vào vs cuối kỳ</h3>
            <div>Đầu vào: <b>{progress?.pre_score != null ? `${Number(progress.pre_score).toFixed(1)}%` : "Chưa có"}</b></div>
            <div>Cuối kỳ: <b>{progress?.post_score != null ? `${Number(progress.post_score).toFixed(1)}%` : `${score.toFixed(1)}%`}</b></div>
            <div>Mức cải thiện: <b style={{ color: delta >= 0 ? "#166534" : "#b91c1c" }}>{delta >= 0 ? "+" : ""}{Number.isFinite(delta) ? delta.toFixed(1) : "0.0"}%</b></div>
            <p style={{ marginBottom: 0, color: "#4338ca" }}>{delta >= 0 ? "Bạn đã tiến bộ rõ rệt sau quá trình học. Tiếp tục phát huy!" : "Kết quả cuối kỳ chưa cao hơn đầu vào. Hãy xem lại phần sai để cải thiện."}</p>
          </div>
        )}

        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <Link to="/assessments"><button style={{ padding: "8px 12px" }}>⬅ Danh sách</button></Link>
          {examMode === "final" ? <button onClick={() => navigate("/final-exam")} style={{ padding: "8px 12px" }}>Về trang Cuối kỳ</button> : null}
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>{data?.title || "Bài kiểm tra"}</h2>
          <div style={{ color: "#666" }}>
            Nhãn: <b>{kindLabelMap[data?.kind] || data?.kind || "Khác"}</b>
          </div>
          {String(data?.kind || "").toLowerCase() === "diagnostic_pre" && (
            <div style={{ marginTop: 8, display: "inline-block", background: "#eff6ff", color: "#1d4ed8", border: "1px solid #93c5fd", borderRadius: 999, padding: "4px 10px", fontWeight: 700 }}>
              ĐÂY LÀ BÀI KIỂM TRA ĐẦU VÀO
            </div>
          )}
          {isFinalExam && (
            <div style={{ marginTop: 8, display: "inline-block", background: "#f5f3ff", color: "#6d28d9", border: "1px solid #c4b5fd", borderRadius: 999, padding: "4px 10px", fontWeight: 700 }}>
              🎓 ĐÂY LÀ BÀI KIỂM TRA CUỐI KỲ
            </div>
          )}
        </div>
        <div style={{ fontWeight: 800, color: timeLeftSec <= 300 ? "#dc2626" : "#111827" }}>⏱ {fmtTime(timeLeftSec)}</div>
      </div>

      {error ? <div style={{ marginTop: 12, color: "#b42318" }}>{error}</div> : null}

      <div style={{ marginTop: 8, color: "#6b7280" }}>Đã trả lời {answeredCount}/{questions.length} câu</div>

      <div style={{ marginTop: 12, display: "grid", gap: 12 }}>
        {questions.map((q, idx) => (
          <div key={q.question_id} style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12, padding: 12 }}>
            <div style={{ color: "#6b7280", fontSize: 13 }}>Câu {idx + 1}</div>
            <div style={{ fontWeight: 700 }}>{q.stem}</div>

            {Array.isArray(q.options) && q.options.length > 0 ? (
              <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
                {q.options.map((op, i) => (
                  <label key={`${q.question_id}-${i}`} style={{ display: "flex", gap: 8, alignItems: "center", border: "1px solid #e5e7eb", borderRadius: 10, padding: 8 }}>
                    <input
                      type="radio"
                      checked={answers[q.question_id]?.answer_index === i}
                      onChange={() => setAnswers((prev) => ({ ...prev, [q.question_id]: { ...prev[q.question_id], answer_index: i } }))}
                      disabled={submitting}
                    />
                    <span>{op}</span>
                  </label>
                ))}
              </div>
            ) : (
              <textarea
                rows={4}
                value={answers[q.question_id]?.answer_text || ""}
                onChange={(e) => setAnswers((prev) => ({ ...prev, [q.question_id]: { ...prev[q.question_id], answer_text: e.target.value } }))}
                placeholder="Nhập câu trả lời..."
                style={{ marginTop: 10, width: "100%", border: "1px solid #e5e7eb", borderRadius: 10, padding: 8 }}
              />
            )}
          </div>
        ))}
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <Link to="/assessments"><button style={{ padding: "8px 12px" }}>⬅ Danh sách</button></Link>
        <button onClick={() => submit(false)} disabled={submitting} style={{ padding: "8px 12px", background: "#2563eb", color: "#fff", border: "none", borderRadius: 8 }}>
          {submitting ? "Đang nộp..." : "Nộp bài"}
        </button>
      </div>

      <div style={{ position: "fixed", top: 16, right: 16, display: "grid", gap: 8, zIndex: 1000 }}>
        {toasts.map((t) => (
          <div key={t.id} style={{ background: "#111827", color: "#fff", padding: "10px 12px", borderRadius: 10, boxShadow: "0 6px 20px rgba(0,0,0,0.25)" }}>
            {t.message}
          </div>
        ))}
      </div>
    </div>
  );
}
