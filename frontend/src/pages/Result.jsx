import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import Card from "../ui/Card";
import Banner from "../ui/Banner";
import Button from "../ui/Button";
import PageHeader from "../ui/PageHeader";

function toArray(value) {
  return Array.isArray(value) ? value : [];
}

function toNumber(value, fallback = 0) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function formatDuration(sec) {
  const total = Math.max(0, Math.floor(toNumber(sec, 0)));
  const hh = Math.floor(total / 3600);
  const mm = Math.floor((total % 3600) / 60);
  const ss = total % 60;
  if (hh > 0) return `${hh}h ${String(mm).padStart(2, "0")}m ${String(ss).padStart(2, "0")}s`;
  return `${mm}m ${String(ss).padStart(2, "0")}s`;
}

function classifyStudent(scorePercent) {
  if (scorePercent >= 85) return "Giỏi";
  if (scorePercent >= 70) return "Khá";
  if (scorePercent >= 50) return "Trung bình";
  return "Yếu";
}

function normalizeQuestionRow(item, index) {
  const selected = item?.student_answer ?? item?.selected_answer ?? item?.user_answer ?? item?.answer ?? item?.answer_text ?? null;
  const correct = item?.correct_answer ?? item?.correct_option ?? item?.expected_answer ?? null;
  const isCorrect = typeof item?.is_correct === "boolean" ? item.is_correct : (selected != null && correct != null ? String(selected) === String(correct) : false);
  const unanswered = selected == null || selected === "" || selected === -1;
  const status = unanswered ? "unanswered" : (isCorrect ? "correct" : "wrong");

  return {
    id: item?.question_id ?? item?.id ?? `q-${index + 1}`,
    question: item?.question ?? item?.question_text ?? item?.content ?? `Câu ${index + 1}`,
    selected,
    correct,
    isCorrect,
    unanswered,
    status,
    difficulty: String(item?.difficulty || "").toLowerCase(),
    topic: item?.topic ?? item?.topic_name ?? "",
  };
}

function normalizeResultPayload(payload) {
  const rawQuestions =
    payload?.questions ||
    payload?.answer_review ||
    payload?.details ||
    payload?.breakdown ||
    [];

  const questionRows = toArray(rawQuestions).map(normalizeQuestionRow);

  const scorePercent = toNumber(
    payload?.score_percent ?? payload?.score ?? payload?.percent,
    0,
  );

  const topicBreakdown = toArray(
    payload?.topic_breakdown ?? payload?.topics ?? payload?.score_by_topic,
  );

  const difficultyBreakdown = payload?.difficulty_breakdown ?? payload?.score_by_difficulty ?? null;

  return {
    scorePercent,
    totalScore: 100,
    correctCount: toNumber(payload?.correct_count, questionRows.filter((q) => q.isCorrect).length),
    totalQuestions: toNumber(payload?.total ?? payload?.total_questions, questionRows.length),
    durationSec: toNumber(payload?.duration_sec ?? payload?.time_spent_sec ?? payload?.time_spent, 0),
    questionRows,
    topicBreakdown,
    difficultyBreakdown,
    raw: payload,
  };
}

function StatCard({ label, value }) {
  return (
    <Card style={{ padding: 16 }}>
      <div style={{ fontSize: 13, color: "#64748b" }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color: "#0f172a", marginTop: 4 }}>{value}</div>
    </Card>
  );
}

export default function Result() {
  const { state } = useLocation();
  const [searchParams] = useSearchParams();
  const { userId } = useAuth();

  const [data, setData] = useState(() => (state?.quizResult ? normalizeResultPayload(state.quizResult) : null));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const attemptId = state?.attemptId ?? searchParams.get("attemptId") ?? searchParams.get("attempt_id");
  const quizSetId = state?.quizSetId ?? searchParams.get("quizSetId") ?? searchParams.get("quiz_set_id");
  const resolvedQuizType = state?.quizType ?? searchParams.get("quizType") ?? searchParams.get("quiz_type") ?? "homework";
  const resolvedUserId = searchParams.get("userId") ?? searchParams.get("user_id") ?? userId;

  useEffect(() => {
    if (state?.quizResult) {
      setData(normalizeResultPayload(state.quizResult));
      return;
    }

    const loadResult = async () => {
      setLoading(true);
      setError("");

      try {
        let resultPayload = null;
        if (attemptId) {
          resultPayload = await apiJson(`/assessments/${attemptId}/result`);
        } else if (quizSetId && resolvedUserId) {
          resultPayload = await apiJson(`/quizzes/${quizSetId}/result?user_id=${resolvedUserId}`);
        } else {
          throw new Error("Thiếu dữ liệu kết quả. Vui lòng mở trang từ luồng nộp bài hoặc truyền attemptId/quizSetId.");
        }

        setData(normalizeResultPayload(resultPayload));
      } catch (e) {
        setError(e?.message || "Không tải được kết quả.");
      } finally {
        setLoading(false);
      }
    };

    loadResult();
  }, [attemptId, quizSetId, resolvedUserId, state]);

  const difficultyStats = useMemo(() => {
    if (!data) return { easy: null, medium: null, hard: null };

    const fromApi = data.difficultyBreakdown;
    if (fromApi && typeof fromApi === "object") {
      return {
        easy: fromApi.easy ?? fromApi.EASY ?? null,
        medium: fromApi.medium ?? fromApi.MEDIUM ?? null,
        hard: fromApi.hard ?? fromApi.HARD ?? null,
      };
    }

    const buckets = {
      easy: { total: 0, correct: 0 },
      medium: { total: 0, correct: 0 },
      hard: { total: 0, correct: 0 },
    };

    data.questionRows.forEach((row) => {
      const key = ["easy", "medium", "hard"].includes(row.difficulty) ? row.difficulty : "medium";
      buckets[key].total += 1;
      if (row.isCorrect) buckets[key].correct += 1;
    });

    return buckets;
  }, [data]);

  const ctaConfig = useMemo(() => {
    if (resolvedQuizType === "diagnostic_pre") {
      return { label: "Bắt đầu học theo lộ trình cá nhân hoá", to: "/learning-path" };
    }
    if (resolvedQuizType === "final") {
      return { label: "Xem báo cáo tổng kết", to: "/progress" };
    }
    return { label: "Tiếp tục bài học", to: "/learning-path" };
  }, [resolvedQuizType]);

  const scoreText = `${Math.round(data?.scorePercent || 0)}/${data?.totalScore || 100}`;

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: 16, display: "grid", gap: 16 }}>
      <PageHeader
        title="Kết quả bài làm"
        subtitle="Hiển thị kết quả ngay sau khi nộp bài"
        breadcrumbs={["Học sinh", "Kết quả"]}
      />

      {loading && <Banner tone="info">Đang tải kết quả...</Banner>}
      {error && <Banner tone="error">{error}</Banner>}

      {data && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
            <StatCard label="Điểm số" value={scoreText} />
            <StatCard label="Phân loại" value={classifyStudent(data.scorePercent)} />
            <StatCard label="Thời gian làm bài" value={formatDuration(data.durationSec)} />
            <StatCard label="Số câu đúng" value={`${data.correctCount}/${data.totalQuestions}`} />
          </div>

          <Card style={{ padding: 16 }}>
            <h3 style={{ marginTop: 0 }}>Điểm theo từng topic</h3>
            {data.topicBreakdown.length ? (
              <div style={{ display: "grid", gap: 8 }}>
                {data.topicBreakdown.map((topic, idx) => (
                  <div key={`${topic?.topic || topic?.name || idx}`} style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid #e2e8f0", paddingBottom: 6 }}>
                    <strong>{topic?.topic || topic?.name || `Topic ${idx + 1}`}</strong>
                    <span>{Math.round(toNumber(topic?.score_percent ?? topic?.score ?? 0))}%</span>
                  </div>
                ))}
              </div>
            ) : (
              <p style={{ color: "#64748b", marginBottom: 0 }}>Không có dữ liệu breakdown theo topic.</p>
            )}
          </Card>

          <Card style={{ padding: 16 }}>
            <h3 style={{ marginTop: 0 }}>Điểm theo độ khó</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 8 }}>
              {["easy", "medium", "hard"].map((level) => {
                const value = difficultyStats[level];
                const text = value && typeof value === "object"
                  ? `${toNumber(value.correct, 0)}/${toNumber(value.total, 0)} đúng`
                  : `${Math.round(toNumber(value, 0))}%`;
                return (
                  <div key={level} style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: 10 }}>
                    <div style={{ fontWeight: 700, textTransform: "uppercase" }}>{level}</div>
                    <div style={{ marginTop: 4, color: "#334155" }}>{text}</div>
                  </div>
                );
              })}
            </div>
          </Card>

          <Card style={{ padding: 16 }}>
            <h3 style={{ marginTop: 0 }}>Chi tiết từng câu</h3>
            {data.questionRows.length ? (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ textAlign: "left", borderBottom: "1px solid #cbd5e1" }}>
                      <th style={{ padding: "8px 6px" }}>Câu hỏi</th>
                      <th style={{ padding: "8px 6px" }}>Đáp án học sinh</th>
                      <th style={{ padding: "8px 6px" }}>Đáp án đúng</th>
                      <th style={{ padding: "8px 6px" }}>Kết quả</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.questionRows.map((row) => {
                      const bg = row.status === "correct" ? "#f0fdf4" : row.status === "wrong" ? "#fef2f2" : "#fefce8";
                      const color = row.status === "correct" ? "#166534" : row.status === "wrong" ? "#b91c1c" : "#a16207";
                      const statusLabel = row.status === "correct" ? "Đúng" : row.status === "wrong" ? "Sai" : "Chưa trả lời";
                      return (
                        <tr key={row.id} style={{ borderBottom: "1px solid #e2e8f0", background: bg }}>
                          <td style={{ padding: "10px 6px" }}>{row.question}</td>
                          <td style={{ padding: "10px 6px" }}>{row.unanswered ? "—" : String(row.selected)}</td>
                          <td style={{ padding: "10px 6px" }}>{row.correct == null ? "—" : String(row.correct)}</td>
                          <td style={{ padding: "10px 6px", color, fontWeight: 700 }}>{statusLabel}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p style={{ color: "#64748b", marginBottom: 0 }}>Không có chi tiết từng câu hỏi.</p>
            )}
          </Card>

          <Card style={{ padding: 16, display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            <div>
              <div style={{ fontWeight: 700 }}>Bạn đã hoàn thành bài {resolvedQuizType}.</div>
              <div style={{ color: "#475569", marginTop: 4 }}>Hệ thống đã chấm và hiển thị kết quả ngay tại đây.</div>
            </div>
            <Link to={ctaConfig.to}>
              <Button variant="primary">{ctaConfig.label}</Button>
            </Link>
          </Card>
        </>
      )}
    </div>
  );
}
