import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import Card from "../ui/Card";
import Button from "../ui/Button";
import Modal from "../ui/Modal";
import Banner from "../ui/Banner";
import Badge from "../ui/Badge";
import Spinner from "../ui/Spinner";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";

function formatClock(totalSec = 0) {
  const sec = Math.max(0, Math.floor(Number(totalSec) || 0));
  const hh = String(Math.floor(sec / 3600)).padStart(2, "0");
  const mm = String(Math.floor((sec % 3600) / 60)).padStart(2, "0");
  const ss = String(sec % 60).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

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
  const { userId } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [timeLeftSec, setTimeLeftSec] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [openSubmitModal, setOpenSubmitModal] = useState(false);
  const [topicIds, setTopicIds] = useState([]);
  const [assessmentId, setAssessmentId] = useState(null);

  const autoSubmittedRef = useRef(false);
  const warningRef = useRef({ ten: false, five: false, one: false });
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

  const unresolvedCount = Math.max(0, questions.length - answeredCount);

  const loadTopics = useCallback(async () => {
    const fromQuery = (searchParams.get("topicIds") || searchParams.get("topic_ids") || "")
      .split(",")
      .map((value) => Number(value.trim()))
      .filter((value) => Number.isFinite(value));

    if (fromQuery.length > 0) {
      setTopicIds([...new Set(fromQuery)]);
      return [...new Set(fromQuery)];
    }

    try {
      const topicRows = await apiJson(`/classrooms/${classroomId}/topics`, { method: "GET" });
      const ids = (Array.isArray(topicRows) ? topicRows : [])
        .map((item) => Number(item?.id ?? item?.topic_id))
        .filter((value) => Number.isFinite(value));
      setTopicIds([...new Set(ids)]);
      return [...new Set(ids)];
    } catch {
      setTopicIds([]);
      return [];
    }
  }, [classroomId, searchParams]);

  const loadFinalExam = useCallback(async () => {
    setLoading(true);
    setError("");
    setWarningMessage("");
    setResult(null);
    autoSubmittedRef.current = false;
    warningRef.current = { ten: false, five: false, one: false };

    try {
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
      setTimeLeftSec(Number.isFinite(durationSec) && durationSec > 0 ? durationSec : 45 * 60);

      if (Array.isArray(data?.topic_ids) && data.topic_ids.length > 0) {
        setTopicIds(data.topic_ids.map((item) => Number(item)).filter((item) => Number.isFinite(item)));
      }
    } catch (e) {
      setError(e?.message || "Không thể tạo bài kiểm tra cuối kỳ.");
    } finally {
      setLoading(false);
    }
  }, [classroomId, loadTopics, userId]);

  useEffect(() => {
    loadFinalExam();
  }, [loadFinalExam]);

  useEffect(() => {
    if (loading || result || submitting || timeLeftSec <= 0) return undefined;

    const timerId = setInterval(() => {
      setTimeLeftSec((prev) => Math.max(0, prev - 1));
    }, 1000);

    return () => clearInterval(timerId);
  }, [loading, result, submitting, timeLeftSec]);

  useEffect(() => {
    if (result || submitting) return;
    if (timeLeftSec <= 600 && !warningRef.current.ten) {
      warningRef.current.ten = true;
      setWarningMessage("⚠️ Cảnh báo: còn 10 phút. Hãy tăng tốc và kiểm tra lại đáp án.");
      return;
    }
    if (timeLeftSec <= 300 && !warningRef.current.five) {
      warningRef.current.five = true;
      setWarningMessage("⚠️ Cảnh báo: còn 5 phút. Chuẩn bị nộp bài ngay.");
      return;
    }
    if (timeLeftSec <= 60 && !warningRef.current.one) {
      warningRef.current.one = true;
      setWarningMessage("🚨 Cảnh báo khẩn: còn 1 phút. Hệ thống sẽ tự động nộp.");
    }
  }, [result, submitting, timeLeftSec]);

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

  useEffect(() => {
    if (timeLeftSec !== 0 || autoSubmittedRef.current || result || loading || submitting) return;
    autoSubmittedRef.current = true;
    submitExam(true);
  }, [loading, result, submitExam, submitting, timeLeftSec]);

  const topicBreakdown = useMemo(() => {
    const stats = {};
    const review = Array.isArray(result?.answer_review) ? result.answer_review : [];

    review.forEach((item) => {
      const key = item?.topic || "Chung";
      if (!stats[key]) stats[key] = { total: 0, correct: 0 };
      stats[key].total += 1;
      if (item?.is_correct) stats[key].correct += 1;
    });

    return Object.entries(stats).map(([topic, value]) => ({
      topic,
      total: value.total,
      correct: value.correct,
      score: percent(value.correct, value.total),
    }));
  }, [result]);

  const difficultyBreakdown = useMemo(() => {
    const stats = { easy: { total: 0, correct: 0 }, medium: { total: 0, correct: 0 }, hard: { total: 0, correct: 0 } };
    const review = Array.isArray(result?.answer_review) ? result.answer_review : [];

    review.forEach((item) => {
      const key = String(item?.difficulty || "medium").toLowerCase();
      if (!stats[key]) return;
      stats[key].total += 1;
      if (item?.is_correct) stats[key].correct += 1;
    });

    return Object.entries(stats).map(([difficulty, value]) => ({
      difficulty,
      total: value.total,
      correct: value.correct,
      score: percent(value.correct, value.total),
    }));
  }, [result]);

  const finalScore = Number(result?.total_score_percent || result?.score_percent || 0);
  const improvement = entryScore > 0 ? Math.round(finalScore - entryScore) : null;

  return (
    <div className="container grid-12">
      <Card className="span-12 stack-md">
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
              {formatClock(timeLeftSec)}
            </div>
            <div style={{ color: "#64748b", fontSize: 12 }}>Đồng hồ đếm ngược, không thể tạm dừng</div>
          </Card>
        </div>

        {warningMessage ? <Banner tone="error">{warningMessage}</Banner> : null}
        {error ? <Banner tone="error">{error}</Banner> : null}
      </Card>

      {loading ? (
        <Card className="span-12">
          <div className="row">
            <Spinner />
            <strong>AI đang tổng hợp bài thi cuối kỳ...</strong>
          </div>
        </Card>
      ) : null}

      {!loading && !result ? (
        <Card className="span-12 stack-md">
          <Banner tone={unresolvedCount > 0 ? "warning" : "success"}>
            Đã trả lời {answeredCount}/{questions.length} câu. {unresolvedCount > 0 ? `Còn ${unresolvedCount} câu chưa trả lời.` : "Bạn đã hoàn thành tất cả câu hỏi."}
          </Banner>

          {questions.map((question, index) => (
            <Card key={question.question_id} className="stack-sm">
              <div style={{ fontWeight: 700 }}>Câu {index + 1}. {question.stem}</div>
              <div className="row" style={{ color: "#64748b", fontSize: 13 }}>
                <span>Topic: {question.topic}</span>
                <span>•</span>
                <span>Độ khó: {question.difficulty}</span>
              </div>

              {question.type === "essay" ? (
                <textarea
                  rows={4}
                  placeholder="Nhập câu trả lời..."
                  value={answers[question.question_id]?.answer_text || ""}
                  onChange={(event) =>
                    setAnswers((prev) => ({
                      ...prev,
                      [question.question_id]: {
                        ...(prev[question.question_id] || {}),
                        answer_text: event.target.value,
                      },
                    }))
                  }
                  style={{ width: "100%", borderRadius: 10, border: "1px solid #cbd5e1", padding: 10 }}
                />
              ) : (
                <div style={{ display: "grid", gap: 8 }}>
                  {question.options.map((option, optionIndex) => (
                    <label key={`${question.question_id}_${optionIndex}`} style={{ display: "flex", gap: 8, cursor: "pointer" }}>
                      <input
                        type="radio"
                        name={question.question_id}
                        checked={answers[question.question_id]?.answer_index === optionIndex}
                        onChange={() =>
                          setAnswers((prev) => ({
                            ...prev,
                            [question.question_id]: {
                              ...(prev[question.question_id] || {}),
                              answer_index: optionIndex,
                            },
                          }))
                        }
                      />
                      <span>{["A", "B", "C", "D"][optionIndex]}. {option}</span>
                    </label>
                  ))}
                </div>
              )}
            </Card>
          ))}

          <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
            <Button variant="ghost" onClick={() => navigate("/assessments")}>Quay lại danh sách bài kiểm tra</Button>
            <Button variant="primary" onClick={() => setOpenSubmitModal(true)} disabled={submitting}>
              {submitting ? "Đang nộp..." : "Nộp bài cuối kỳ"}
            </Button>
          </div>
        </Card>
      ) : null}

      {!loading && result ? (
        <Card className="span-12 stack-md">
          <h2 style={{ margin: 0 }}>Kết quả bài kiểm tra cuối kỳ</h2>
          <Banner tone="success">
            Điểm tổng: <strong>{finalScore}%</strong> • Xếp loại: <strong>{classify(finalScore)}</strong>
          </Banner>

          {improvement != null ? (
            <Banner tone={improvement >= 0 ? "success" : "error"}>
              Bạn đã cải thiện {improvement >= 0 ? `+${improvement}%` : `${improvement}%`} so với bài kiểm tra đầu vào.
            </Banner>
          ) : null}

          <div style={{ display: "grid", gap: 10 }}>
            <h3 style={{ marginBottom: 0 }}>Breakdown theo từng chủ đề</h3>
            {topicBreakdown.length === 0 ? (
              <div style={{ color: "#64748b" }}>Chưa có dữ liệu breakdown theo chủ đề.</div>
            ) : (
              topicBreakdown.map((item) => (
                <Card key={item.topic}>
                  <strong>{item.topic}</strong> — {item.correct}/{item.total} câu đúng ({item.score}%)
                </Card>
              ))
            )}
          </div>

          <div style={{ display: "grid", gap: 10 }}>
            <h3 style={{ marginBottom: 0 }}>Breakdown theo độ khó</h3>
            {difficultyBreakdown.map((item) => (
              <Card key={item.difficulty}>
                <strong>{item.difficulty}</strong> — {item.correct}/{item.total} câu đúng ({item.score}%)
              </Card>
            ))}
          </div>

          <div className="row" style={{ justifyContent: "space-between" }}>
            <Link to="/progress" style={{ textDecoration: "none" }}>
              <Button variant="primary">Xem báo cáo tổng kết của bạn</Button>
            </Link>
            <Button variant="ghost" onClick={loadFinalExam}>Tạo đề cuối kỳ mới</Button>
          </div>
        </Card>
      ) : null}

      <Modal
        open={openSubmitModal}
        title="Xác nhận nộp bài cuối kỳ"
        onClose={() => setOpenSubmitModal(false)}
        actions={(
          <>
            <Button variant="ghost" onClick={() => setOpenSubmitModal(false)} disabled={submitting}>Làm tiếp</Button>
            <Button variant="primary" onClick={() => submitExam(false)} disabled={submitting}>
              {submitting ? "Đang nộp..." : "Xác nhận nộp"}
            </Button>
          </>
        )}
      >
        Bạn còn <strong>{unresolvedCount}</strong> câu chưa trả lời. Sau khi nộp sẽ không thể chỉnh sửa.
      </Modal>
    </div>
  );
}
