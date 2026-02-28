import { useCallback, useEffect, useMemo, useRef, useState } from "react";

function formatTime(totalSeconds) {
  const sec = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  const mm = String(Math.floor(sec / 60)).padStart(2, "0");
  const ss = String(sec % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function getQuestionId(question, index) {
  return question?.id ?? question?.question_id ?? `question-${index}`;
}

function isAnswered(question, answer) {
  if (question?.type === "essay") {
    return typeof answer?.answer_text === "string" && answer.answer_text.trim().length > 0;
  }
  return Number.isInteger(answer?.answer_index);
}

export default function TimedExam({ questions = [], durationSeconds = 0, onSubmit }) {
  const [answers, setAnswers] = useState({});
  const [timeLeft, setTimeLeft] = useState(Math.max(0, Number(durationSeconds) || 0));
  const [isSubmitting, setIsSubmitting] = useState(false);

  const hasTimer = Number(durationSeconds) > 0;
  const startedAtRef = useRef(0);
  const submittedRef = useRef(false);

  useEffect(() => {
    startedAtRef.current = Date.now();
  }, []);

  const answeredCount = useMemo(() => {
    return questions.reduce((count, question, index) => {
      const qid = getQuestionId(question, index);
      return count + (isAnswered(question, answers[qid]) ? 1 : 0);
    }, 0);
  }, [answers, questions]);

  const submitExam = useCallback(
    async ({ force = false } = {}) => {
      if (submittedRef.current || isSubmitting) return;

      const unanswered = Math.max(0, questions.length - answeredCount);
      if (!force) {
        const confirmed = window.confirm(`Bạn còn ${unanswered} câu chưa trả lời, xác nhận nộp?`);
        if (!confirmed) return;
      }

      submittedRef.current = true;
      setIsSubmitting(true);

      const timeSpent = Math.max(0, Math.round((Date.now() - startedAtRef.current) / 1000));
      await Promise.resolve(onSubmit?.(answers, timeSpent));
      setIsSubmitting(false);
    },
    [answeredCount, answers, isSubmitting, onSubmit, questions.length]
  );

  useEffect(() => {
    if (!hasTimer || submittedRef.current || isSubmitting) return;

    const timerId = window.setInterval(() => {
      setTimeLeft((prev) => Math.max(0, prev - 1));
    }, 1000);

    return () => window.clearInterval(timerId);
  }, [hasTimer, isSubmitting]);

  useEffect(() => {
    if (!hasTimer || timeLeft > 0 || submittedRef.current) return;

    const timeoutId = window.setTimeout(() => {
      submitExam({ force: true });
    }, 0);

    return () => window.clearTimeout(timeoutId);
  }, [hasTimer, submitExam, timeLeft]);

  const setMcqAnswer = (questionId, answerIndex) => {
    setAnswers((prev) => ({
      ...prev,
      [questionId]: {
        ...(prev[questionId] || {}),
        answer_index: answerIndex,
      },
    }));
  };

  const setEssayAnswer = (questionId, text) => {
    setAnswers((prev) => ({
      ...prev,
      [questionId]: {
        ...(prev[questionId] || {}),
        answer_text: text,
      },
    }));
  };

  const progressPercent = questions.length > 0 ? (answeredCount / questions.length) * 100 : 0;

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: 16 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 12,
          flexWrap: "wrap",
          marginBottom: 14,
        }}
      >
        <h2 style={{ margin: 0 }}>Bài kiểm tra</h2>
        <div
          style={{
            fontWeight: 800,
            fontSize: 20,
            color: timeLeft < 60 ? "#dc2626" : "#0f172a",
            minWidth: 88,
            textAlign: "right",
          }}
        >
          {hasTimer ? formatTime(timeLeft) : "Không giới hạn"}
        </div>
      </div>

      <div style={{ marginBottom: 14 }}>
        <div style={{ marginBottom: 6, fontWeight: 600 }}>Đã làm {answeredCount}/{questions.length} câu</div>
        <div style={{ height: 10, borderRadius: 999, background: "#e2e8f0", overflow: "hidden" }}>
          <div
            style={{
              width: `${Math.max(0, Math.min(100, progressPercent))}%`,
              height: "100%",
              background: "#2563eb",
            }}
          />
        </div>
      </div>

      <div style={{ display: "grid", gap: 12 }}>
        {questions.map((question, index) => {
          const qid = getQuestionId(question, index);
          const options = Array.isArray(question?.options) && question.options.length > 0
            ? question.options
            : ["A", "B", "C", "D"];
          const questionType = question?.type || "mcq";

          return (
            <div key={qid} style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 14, background: "#fff" }}>
              <div style={{ fontWeight: 700, marginBottom: 10 }}>Câu {index + 1}: {question?.question || question?.content}</div>

              {questionType === "essay" ? (
                <textarea
                  value={answers[qid]?.answer_text || ""}
                  onChange={(e) => setEssayAnswer(qid, e.target.value)}
                  rows={5}
                  placeholder="Nhập câu trả lời của bạn..."
                  style={{ width: "100%", borderRadius: 8, border: "1px solid #cbd5e1", padding: 10 }}
                />
              ) : (
                <div style={{ display: "grid", gap: 8 }}>
                  {options.slice(0, 4).map((option, optionIndex) => {
                    const label = ["A", "B", "C", "D"][optionIndex] || "";
                    return (
                      <label
                        key={`${qid}-${optionIndex}`}
                        style={{ display: "flex", gap: 8, alignItems: "flex-start", cursor: "pointer" }}
                      >
                        <input
                          type="radio"
                          name={`question-${qid}`}
                          checked={answers[qid]?.answer_index === optionIndex}
                          onChange={() => setMcqAnswer(qid, optionIndex)}
                        />
                        <span>
                          <strong>{label}.</strong> {option?.label || option?.text || option}
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div style={{ marginTop: 16, display: "flex", justifyContent: "flex-end" }}>
        <button
          type="button"
          onClick={() => submitExam({ force: false })}
          disabled={isSubmitting}
          style={{
            border: 0,
            borderRadius: 10,
            background: "#2563eb",
            color: "#fff",
            padding: "10px 16px",
            cursor: isSubmitting ? "not-allowed" : "pointer",
            opacity: isSubmitting ? 0.7 : 1,
          }}
        >
          {isSubmitting ? "Đang nộp..." : "Nộp bài"}
        </button>
      </div>
    </div>
  );
}
