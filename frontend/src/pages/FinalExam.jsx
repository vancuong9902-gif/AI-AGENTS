import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useExamTimer } from "../hooks/useExamTimer";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import Card from "../ui/Card";
import Button from "../ui/Button";
import Banner from "../ui/Banner";
import useExamTimer from "../hooks/useExamTimer";

const PHASES = {
  ELIGIBILITY: "eligibility_check",
  GENERATING: "generating",
  INSTRUCTIONS: "instructions",
  ACTIVE: "active",
  RESULT: "result",
};

const asPercent = (n) => Math.max(0, Math.min(100, Math.round(Number(n) || 0)));
const formatClock = (s) => `${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
function classify(score = 0) {
  const safeScore = Number(score) || 0;
  if (safeScore >= 85) return "Giỏi";
  if (safeScore >= 70) return "Khá";
  if (safeScore >= 50) return "Trung bình";
  return "Yếu";
}

function parseQuestion(question, index) {
  const normalizedOptions = (Array.isArray(question?.options) ? question.options : []).slice(0, 4).map((option, idx) => {
    if (typeof option === "string") return option;
    return option?.label || option?.text || option?.content || `Lựa chọn ${idx + 1}`;
  });

  return {
    question_id: question?.question_id ?? question?.id ?? `final_q_${index}`,
    stem: question?.stem || question?.question_text || question?.content || `Câu hỏi ${index + 1}`,
    topic: question?.topic || question?.topic_name || "Chung",
    difficulty: String(question?.difficulty || "medium").toLowerCase(),
    type: question?.type || "mcq",
    options: normalizedOptions,
  };
}

function percent(correct = 0, total = 0) {
  if (!total) return 0;
  return Math.round((correct / total) * 100);
}

export default function FinalExam() {
  const { classroomId } = useParams();
  const { userId, role } = useAuth();
  const nav = useNavigate();

  const [phase, setPhase] = useState(PHASES.ELIGIBILITY);
  const [eligibility, setEligibility] = useState(null);
  const [error, setError] = useState("");

  const [jobId, setJobId] = useState(null);
  const [genStatus, setGenStatus] = useState({ progress: 0, topics_count: 0, status: "idle" });

  const [meta, setMeta] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [warning, setWarning] = useState("");
  const [durationSeconds, setDurationSeconds] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [openSubmitModal, setOpenSubmitModal] = useState(false);
  const [topicIds, setTopicIds] = useState([]);
  const [assessmentId, setAssessmentId] = useState(null);

  const autoSubmittedRef = useRef(false);
  const [warningMessage, setWarningMessage] = useState("");

  const entryScore = useMemo(() => {
    const fromQuery = Number(searchParams.get("entryScore") || searchParams.get("entry_score") || 0);
    const fromStorage = Number(localStorage.getItem("entry_test_score") || 0);
    return Number.isFinite(fromQuery) && fromQuery > 0 ? fromQuery : fromStorage;
  }, [searchParams]);

  const answeredCount = useMemo(
    () => Object.values(answers).filter((answer) => Number.isInteger(answer?.answer_index) || (answer?.answer_text || "").trim()).length,
    [answers],
  );

  const warningRef = useRef({ ten: false, five: false });
  const { timeLeftSec } = useExamTimer(meta?.duration_seconds || 0, { enabled: phase === PHASES.ACTIVE && !result });

  const entryScore = Number(localStorage.getItem("entry_test_score") || 0);

  const loadEligibility = useCallback(async () => {
    if (!classroomId || !userId) return;
    setError("");
    try {
      const data = await apiJson(`/v1/lms/final-exam/eligibility?classroomId=${classroomId}&userId=${userId}`);
      setEligibility(data);
    } catch (e) {
      setError(e?.message || "Không thể kiểm tra điều kiện dự thi.");
    }
  }, [classroomId, userId]);

  useEffect(() => {
    loadEligibility();
  }, [loadEligibility]);
  const loadFinalExam = useCallback(async () => {
    setLoading(true);
    setError("");
    setWarningMessage("");
    setResult(null);
    autoSubmittedRef.current = false;

  const startGenerating = async () => {
    setError("");
    setPhase(PHASES.GENERATING);
    try {
      const data = await apiJson(`/v1/lms/final-exam/generate?classroomId=${classroomId}&userId=${userId}`, { method: "POST" });
      setJobId(data?.jobId);
      const resolvedTopicIds = await loadTopics();
      const data = await apiJson("/v1/lms/generate-final", {
        method: "POST",
        body: {
          classroomId: Number(classroomId),
          userId: Number(userId),
          topicIds: resolvedTopicIds,
        },
      });

      const normalizedQuestions = (Array.isArray(data?.questions) ? data.questions : []).map(parseQuestion);
      if (!normalizedQuestions.length) throw new Error("Không tạo được câu hỏi cuối kỳ.");

      const durationSec = Number(data?.duration_seconds || data?.time_limit_seconds || 45 * 60);
      setQuestions(normalizedQuestions);
      setAnswers({});
      setAssessmentId(data?.assessment_id || data?.quiz_id || data?.id || null);
      setDurationSeconds(Number.isFinite(durationSec) && durationSec > 0 ? durationSec : 45 * 60);

      if (Array.isArray(data?.topic_ids) && data.topic_ids.length > 0) {
        setTopicIds(data.topic_ids.map((item) => Number(item)).filter((item) => Number.isFinite(item)));
      }
    } catch (e) {
      setError(e?.message || "Không thể khởi tạo đề thi cuối kỳ.");
      setPhase(PHASES.ELIGIBILITY);
    }
  };

  useEffect(() => {
    if (!jobId || phase !== PHASES.GENERATING) return undefined;
    const timer = window.setInterval(async () => {
      try {
        const data = await apiJson(`/v1/lms/final-exam/status?jobId=${jobId}`);
        setGenStatus(data);
        if (data?.status === "completed") {
          const res = data?.result || {};
          setMeta(res);
          setQuestions(Array.isArray(res.questions) ? res.questions : []);
          setPhase(PHASES.INSTRUCTIONS);
          window.clearInterval(timer);
        }
      } catch (e) {
        setError(e?.message || "Không lấy được trạng thái tạo đề.");
        window.clearInterval(timer);
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [jobId, phase]);

  useEffect(() => {
    if (phase !== PHASES.ACTIVE) return;
    if (timeLeftSec <= 600 && !warningRef.current.ten) {
      warningRef.current.ten = true;
      setWarning("⚠️ Còn 10 phút, hãy tăng tốc và rà soát đáp án.");
    }
    if (timeLeftSec <= 300 && !warningRef.current.five) {
      warningRef.current.five = true;
      setWarning("🚨 Còn 5 phút, chuẩn bị nộp bài.");
    }
    if (timeLeftSec <= 0 && !submitting && !result) {
      submitExam(true);
    }
  }, [phase, result, submitting, timeLeftSec]);
  const submitExam = useCallback(
    async (autoSubmit = false) => {
      if (submitting || result) return;
      if (!assessmentId) {
        setError("Thiếu mã bài thi để nộp.");
        return;
      }

      setSubmitting(true);
      setError("");

      try {
        const payload = {
          user_id: Number(userId),
          duration_sec: 0,
          answers: questions.map((question) => ({
            question_id: question.question_id,
            answer_index: answers[question.question_id]?.answer_index ?? null,
            answer_text: answers[question.question_id]?.answer_text ?? null,
            selected_option: answers[question.question_id]?.answer_index ?? null,
          })),
          auto_submitted: autoSubmit,
        };

        const data = await apiJson(`/assessments/${assessmentId}/submit`, { method: "POST", body: payload });
        setResult(data);
        localStorage.setItem("final_exam_score", String(Number(data?.total_score_percent || data?.score_percent || 0)));
      } catch (e) {
        setError(e?.message || "Nộp bài cuối kỳ thất bại.");
      } finally {
        setSubmitting(false);
        setOpenSubmitModal(false);
      }
    },
    [answers, assessmentId, questions, result, submitting, userId],
  );

  const { timeLeft: timeLeftSec, formattedTime } = useExamTimer({
    totalSeconds: !loading && !result && !submitting ? durationSeconds : 0,
    onWarning: (secsLeft) => {
      if (secsLeft === 600) setWarningMessage("⏰ Còn 10 phút. Hãy rà soát lại đáp án.");
      if (secsLeft === 300) setWarningMessage("⚠️ Còn 5 phút. Chuẩn bị nộp bài.");
      if (secsLeft === 60) setWarningMessage("🚨 Cảnh báo khẩn: còn 1 phút. Hệ thống sẽ tự động nộp.");
    },
    onTimeUp: () => {
      if (!autoSubmittedRef.current && !result && !loading && !submitting) {
        autoSubmittedRef.current = true;
        submitExam(true);
      }
    },
  });


  const topicBreakdown = useMemo(() => {
    const stats = {};
    const review = Array.isArray(result?.answer_review) ? result.answer_review : [];

  const submitExam = async (autoSubmitted = false) => {
    if (!meta?.assessment_id || submitting) return;
    setSubmitting(true);
    try {
      const payload = {
        user_id: Number(userId),
        duration_sec: 0,
        auto_submitted: autoSubmitted,
        answers: questions.map((q, idx) => ({
          question_id: q.question_id || q.id || `final_${idx + 1}`,
          answer_index: answers[q.question_id || q.id]?.answer_index ?? null,
          answer_text: answers[q.question_id || q.id]?.answer_text ?? null,
        })),
      };
      const data = await apiJson(`/assessments/${meta.assessment_id}/submit`, { method: "POST", body: payload });
      setResult(data);
      localStorage.setItem("final_exam_score", String(Number(data?.total_score_percent || data?.score_percent || 0)));
      setPhase(PHASES.RESULT);
    } catch (e) {
      setError(e?.message || "Nộp bài thất bại.");
    } finally {
      setSubmitting(false);
    }
  };

  const score = Number(result?.total_score_percent || result?.score_percent || 0);
  const diff = entryScore > 0 ? Math.round(score - entryScore) : null;

  const difficulty = useMemo(() => {
    const d = meta?.difficulty || {};
    return `${Number(d.easy || 0)}/${Number(d.medium || 0)}/${Number(d.hard || 0)}`;
  }, [meta]);

  return (
    <div className="container grid-12">
      <Card className="span-12 stack-md">
        <h1 style={{ margin: 0 }}>🎓 BÀI KIỂM TRA CUỐI KỲ</h1>
        <div style={{ color: "#64748b" }}>Lớp #{classroomId} • User #{userId} • Vai trò: {role || "student"}</div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 30 }}>BÀI KIỂM TRA CUỐI KỲ</h1>
            <div style={{ marginTop: 8 }}>
              <Badge tone="warning" style={{ background: "#fef3c7", color: "#991b1b", border: "1px solid #f59e0b" }}>
                Đây là bài kiểm tra chính thức - Câu hỏi hoàn toàn mới
              </Badge>
            </div>
            <p style={{ marginBottom: 0, color: "#475569" }}>Bao gồm tất cả {topicIds.length} chủ đề đã học</p>
          </div>
          <Card style={{ minWidth: 220 }}>
            <div style={{ fontSize: 13, color: "#475569" }}>Thời gian còn lại</div>
            <div style={{ fontSize: 34, fontWeight: 800, color: timeLeftSec <= 60 ? "#b91c1c" : "#0f172a", letterSpacing: 1 }}>
              {formattedTime.includes(":") && formattedTime.split(":").length === 2 ? `00:${formattedTime}` : formattedTime}
            </div>
            <div style={{ color: "#64748b", fontSize: 12 }}>Đồng hồ đếm ngược, không thể tạm dừng</div>
          </Card>
        </div>

        {warningMessage ? <Banner tone="error">{warningMessage}</Banner> : null}
        {error ? <Banner tone="error">{error}</Banner> : null}
        {warning ? <Banner tone="warning">{warning}</Banner> : null}
      </Card>

      {phase === PHASES.ELIGIBILITY && (
        <Card className="span-12 stack-md">
          <h3 style={{ margin: 0 }}>Kiểm tra điều kiện dự thi</h3>
          {(eligibility?.conditions || []).map((cond) => (
            <div key={cond.label} style={{ border: "1px solid #e2e8f0", borderRadius: 12, padding: 12 }}>
              <div style={{ fontWeight: 700 }}>{cond.met ? "✅" : "❌"} {cond.label}</div>
              <div style={{ color: "#475569" }}>{cond.detail || ""}</div>
              {typeof cond.progress_pct === "number" ? <div style={{ marginTop: 6, color: "#0f172a" }}>Tiến độ: {asPercent(cond.progress_pct)}%</div> : null}
            </div>
          ))}
          {eligibility?.is_eligible ? (
            <Button variant="primary" onClick={startGenerating}>Bắt đầu tạo đề thi</Button>
          ) : (
            <Banner tone="warning">Bạn chưa đủ điều kiện thi. Điều kiện đang chặn: {eligibility?.blocking_condition || "—"}</Banner>
          )}
        </Card>
      )}

      {phase === PHASES.GENERATING && (
        <Card className="span-12 stack-md" style={{ padding: 24 }}>
          <h2 style={{ margin: 0 }}>🤖 AI đang tổng hợp đề thi cuối kỳ...</h2>
          <div>✅ Phân tích kết quả học tập</div>
          <div>✅ Loại trừ câu hỏi đã dùng</div>
          <div>⏳ Tạo câu hỏi mới theo {genStatus?.topics_count || 0} chủ đề</div>
          <div>⏳ Cân bằng độ khó...</div>
          <div style={{ marginTop: 10 }}>[{"█".repeat(Math.floor((genStatus.progress || 0) / 10)).padEnd(10, "░")}] {asPercent(genStatus.progress)}%</div>
        </Card>
      )}

      {phase === PHASES.INSTRUCTIONS && (
        <Card className="span-12 stack-md">
          <Banner tone="success">🆕 Toàn bộ câu hỏi HOÀN TOÀN MỚI (khác 100% với bài đầu vào)</Banner>
          <div>• Tổng: {questions.length} câu ({difficulty})</div>
          <div>• Thời gian: {Math.round((meta?.duration_seconds || 0) / 60)} phút</div>
          <div>• Bao gồm {meta?.topic_count || 0} chủ đề đã học</div>
          <div>• Độ khó: Tổng hợp (Easy + Medium + Hard)</div>
          <Banner tone="warning">Sau khi bắt đầu, đồng hồ chạy liên tục. Không thể tạm dừng. Hết giờ tự động nộp.</Banner>
          <Button variant="primary" onClick={() => setPhase(PHASES.ACTIVE)}>Bắt đầu làm bài →</Button>
        </Card>
      )}

      {phase === PHASES.ACTIVE && (
        <Card className="span-12 stack-md">
          <div style={{ fontWeight: 800 }}>⏱ {formatClock(timeLeftSec)}</div>
          {questions.map((q, idx) => {
            const qid = q.question_id || q.id || `q_${idx + 1}`;
            const options = Array.isArray(q.options) ? q.options : [];
            return (
              <div key={qid} style={{ border: "1px solid #e2e8f0", borderRadius: 12, padding: 12 }}>
                <div style={{ fontWeight: 700 }}>Câu {idx + 1}: {q.stem || q.question_text}</div>
                {options.map((opt, oi) => (
                  <label key={`${qid}-${oi}`} style={{ display: "block", marginTop: 6 }}>
                    <input type="radio" name={qid} checked={answers[qid]?.answer_index === oi} onChange={() => setAnswers((m) => ({ ...m, [qid]: { answer_index: oi } }))} /> {String.fromCharCode(65 + oi)}. {typeof opt === "string" ? opt : opt?.label || opt?.text}
                  </label>
                ))}
              </div>
            );
          })}
          <Button variant="primary" onClick={() => submitExam(false)} disabled={submitting}>{submitting ? "Đang nộp..." : "Nộp bài"}</Button>
        </Card>
      )}

      {phase === PHASES.RESULT && (
        <Card className="span-12 stack-md">
          <h3 style={{ margin: 0 }}>Kết quả bài thi cuối kỳ</h3>
          <Banner tone="success">Điểm cuối kỳ: <strong>{Math.round(score)}%</strong></Banner>
          {diff != null ? <Banner tone={diff >= 0 ? "success" : "error"}>So với diagnostic: {diff >= 0 ? `+${diff}` : diff}%</Banner> : null}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Button variant="primary" onClick={() => nav("/progress")}>Xem báo cáo đầy đủ gửi cho giáo viên</Button>
            <Button variant="ghost" onClick={() => nav("/learning-path")}>Quay lại Learning Path</Button>
          </div>
        </Card>
      )}
    </div>
  );
}
