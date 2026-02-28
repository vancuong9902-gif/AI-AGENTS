import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { apiJson } from "../lib/api";

const LEVELS = [
  { key: "easy", label: "Dễ" },
  { key: "medium", label: "Trung bình" },
  { key: "hard", label: "Khó" },
];

function normalizeQuestions(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.questions)) return payload.questions;
  if (Array.isArray(payload?.items)) return payload.items;
  return [];
}

function getQuestionId(question, index) {
  return String(question?.question_id ?? question?.id ?? `q-${index}`);
}

function getQuestionText(question) {
  return question?.stem || question?.question || question?.text || "(Chưa có nội dung câu hỏi)";
}

function getOptions(question) {
  if (Array.isArray(question?.options)) return question.options;
  if (Array.isArray(question?.choices)) return question.choices;
  return [];
}

function resolveCorrectIndex(question) {
  const candidates = [
    question?.correct_option,
    question?.correct_answer,
    question?.answer,
    question?.answer_index,
    question?.correct_index,
  ];

  for (const value of candidates) {
    if (Number.isInteger(value)) return Number(value);
    if (typeof value === "string") {
      const asNumber = Number(value);
      if (Number.isInteger(asNumber)) return asNumber;
      const upper = value.trim().toUpperCase();
      if (/^[A-D]$/.test(upper)) return upper.charCodeAt(0) - 65;
    }
  }
  return null;
}

export default function StudentPractice() {
  const { topicId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();

  const userId = localStorage.getItem("user_id") || "anonymous";
  const storageKey = `practice_${topicId}_${userId}`;

  const [topicName, setTopicName] = useState(`Topic #${topicId}`);
  const initialLevel = new URLSearchParams(location.search).get("level");
  const [activeLevel, setActiveLevel] = useState(LEVELS.some((x) => x.key === initialLevel) ? initialLevel : "easy");
  const [questionsByLevel, setQuestionsByLevel] = useState({ easy: [], medium: [], hard: [] });
  const [loadingByLevel, setLoadingByLevel] = useState({ easy: false, medium: false, hard: false });
  const [errorByLevel, setErrorByLevel] = useState({ easy: "", medium: "", hard: "" });
  const [answersByLevel, setAnswersByLevel] = useState({ easy: {}, medium: {}, hard: {} });
  const [feedbackByLevel, setFeedbackByLevel] = useState({ easy: {}, medium: {}, hard: {} });

  useEffect(() => {
    let cancelled = false;

    async function loadTopicName() {
      try {
        const topic = await apiJson(`/documents/topics/${topicId}`);
        if (!cancelled && topic?.title) setTopicName(topic.title);
      } catch {
        // keep fallback name
      }
    }

    function restoreProgress() {
      try {
        const raw = localStorage.getItem(storageKey);
        if (!raw) return;
        const parsed = JSON.parse(raw);
        if (parsed?.answersByLevel) setAnswersByLevel(parsed.answersByLevel);
        if (parsed?.feedbackByLevel) setFeedbackByLevel(parsed.feedbackByLevel);
      } catch {
        // ignore corrupted local storage
      }
    }

    restoreProgress();
    loadTopicName();
    return () => {
      cancelled = true;
    };
  }, [storageKey, topicId]);

  useEffect(() => {
    localStorage.setItem(storageKey, JSON.stringify({ answersByLevel, feedbackByLevel }));
  }, [answersByLevel, feedbackByLevel, storageKey]);

  async function loadQuestions(level) {
    if (!topicId || loadingByLevel[level]) return;

    setLoadingByLevel((prev) => ({ ...prev, [level]: true }));
    setErrorByLevel((prev) => ({ ...prev, [level]: "" }));

    try {
      const data = await apiJson(`/quiz/by-topic?topic_id=${topicId}&level=${level}&user_id=${userId}`);
      const items = normalizeQuestions(data?.questions || data);
      setQuestionsByLevel((prev) => ({ ...prev, [level]: items }));
    } catch (error) {
      setErrorByLevel((prev) => ({ ...prev, [level]: error?.message || "Không tải được câu hỏi" }));
    } finally {
      setLoadingByLevel((prev) => ({ ...prev, [level]: false }));
    }
  }

  useEffect(() => {
    loadQuestions(activeLevel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeLevel, topicId]);

  const completedByLevel = useMemo(() => {
    return LEVELS.reduce((acc, level) => {
      const key = level.key;
      const total = questionsByLevel[key].length;
      const answered = Object.keys(feedbackByLevel[key] || {}).length;
      acc[key] = {
        done: Math.min(total, answered),
        total: total || 5,
      };
      return acc;
    }, {});
  }, [feedbackByLevel, questionsByLevel]);

  const unlockedLevels = useMemo(() => ({ easy: true, medium: true, hard: true }), []);

  function onSelectOption(level, questionId, optionIndex) {
    setAnswersByLevel((prev) => ({
      ...prev,
      [level]: {
        ...prev[level],
        [questionId]: optionIndex,
      },
    }));
  }

  function onEssayChange(level, questionId, text) {
    setAnswersByLevel((prev) => ({
      ...prev,
      [level]: {
        ...prev[level],
        [questionId]: text,
      },
    }));

    if (String(text || "").trim()) {
      setFeedbackByLevel((prev) => ({
        ...prev,
        [level]: {
          ...prev[level],
          [questionId]: {
            isCorrect: null,
            message: "Đã lưu câu trả lời tự luận.",
          },
        },
      }));
    }
  }

  function checkAnswer(level, question, index) {
    const questionId = getQuestionId(question, index);
    const selected = answersByLevel[level]?.[questionId];

    if (!Number.isInteger(selected)) {
      setFeedbackByLevel((prev) => ({
        ...prev,
        [level]: {
          ...prev[level],
          [questionId]: {
            isCorrect: false,
            message: "Bạn chưa chọn đáp án.",
          },
        },
      }));
      return;
    }

    const correctIndex = resolveCorrectIndex(question);
    if (correctIndex === null) {
      setFeedbackByLevel((prev) => ({
        ...prev,
        [level]: {
          ...prev[level],
          [questionId]: {
            isCorrect: null,
            message: "Đã ghi nhận câu trả lời.",
          },
        },
      }));
      return;
    }

    const isCorrect = Number(selected) === Number(correctIndex);
    const explanation = question?.explanation ? ` Giải thích: ${question.explanation}` : "";
    const correctLabel = String.fromCharCode(65 + correctIndex);

    setFeedbackByLevel((prev) => ({
      ...prev,
      [level]: {
        ...prev[level],
        [questionId]: {
          isCorrect,
          message: isCorrect
            ? `Đúng!${explanation}`
            : `Sai. Đáp án đúng là: ${correctLabel}.${explanation}`,
        },
      },
    }));
  }

  const levelQuestions = questionsByLevel[activeLevel] || [];
  const totalDone = Object.values(completedByLevel).reduce((sum, item) => sum + (item?.done || 0), 0);
  const totalCount = Object.values(completedByLevel).reduce((sum, item) => sum + (item?.total || 0), 0);
  const progressPercent = Math.round((totalDone / Math.max(1, totalCount)) * 100);

  return (
    <div style={{ maxWidth: 1120, margin: "0 auto", padding: 16, display: "grid", gridTemplateColumns: "2.4fr 1fr", gap: 16 }}>
      <main style={{ border: "1px solid #e5e7eb", borderRadius: 16, background: "#fff", padding: 16 }}>
        <h1 style={{ margin: 0 }}>Bài tập: {topicName}</h1>
        <div style={{ marginTop: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, color: "#475569" }}>
            <span>Tiến độ tổng</span>
            <strong>{totalDone}/{totalCount}</strong>
          </div>
          <div style={{ background: "#e2e8f0", borderRadius: 999, overflow: "hidden", height: 10 }}>
            <div style={{ width: `${progressPercent}%`, height: "100%", background: "#2563eb" }} />
          </div>
        </div>

        <div style={{ display: "flex", gap: 10, marginTop: 16, borderBottom: "1px solid #e2e8f0", paddingBottom: 12 }}>
          {LEVELS.map((level) => {
            const unlocked = unlockedLevels[level.key];
            const isActive = activeLevel === level.key;
            return (
              <button
                key={level.key}
                type="button"
                onClick={() => unlocked && setActiveLevel(level.key)}
                disabled={!unlocked}
                style={{
                  border: "none",
                  borderRadius: 10,
                  padding: "8px 14px",
                  background: isActive ? "#1d4ed8" : "#e2e8f0",
                  color: isActive ? "#fff" : "#0f172a",
                  cursor: unlocked ? "pointer" : "not-allowed",
                  opacity: unlocked ? 1 : 0.55,
                }}
              >
                {level.label}
              </button>
            );
          })}
        </div>

        {loadingByLevel[activeLevel] && <p style={{ color: "#64748b" }}>Đang tải bài tập...</p>}
        {errorByLevel[activeLevel] && <p style={{ color: "#dc2626" }}>{errorByLevel[activeLevel]}</p>}

        <div style={{ display: "grid", gap: 12, marginTop: 14 }}>
          {levelQuestions.map((question, idx) => {
            const questionId = getQuestionId(question, idx);
            const options = getOptions(question);
            const feedback = feedbackByLevel[activeLevel]?.[questionId];
            const isEssay = (question?.type || "mcq") === "essay" || options.length === 0;

            return (
              <article key={questionId} style={{ border: "1px solid #e2e8f0", borderRadius: 12, padding: 14 }}>
                <div style={{ fontWeight: 700 }}>Câu {idx + 1}</div>
                <p style={{ marginBottom: 12 }}>{getQuestionText(question)}</p>

                {isEssay ? (
                  <textarea
                    rows={4}
                    value={answersByLevel[activeLevel]?.[questionId] || ""}
                    onChange={(event) => onEssayChange(activeLevel, questionId, event.target.value)}
                    placeholder="Nhập câu trả lời của bạn..."
                    style={{ width: "100%", borderRadius: 10, border: "1px solid #cbd5e1", padding: 10 }}
                  />
                ) : (
                  <div style={{ display: "grid", gap: 8 }}>
                    {options.map((option, optionIndex) => {
                      const selected = answersByLevel[activeLevel]?.[questionId] === optionIndex;
                      return (
                        <label key={`${questionId}-${optionIndex}`} style={{ display: "flex", gap: 8, background: selected ? "#dbeafe" : "#f8fafc", borderRadius: 8, padding: 8 }}>
                          <input
                            type="radio"
                            name={`${activeLevel}-${questionId}`}
                            checked={selected}
                            onChange={() => onSelectOption(activeLevel, questionId, optionIndex)}
                          />
                          <span>{String.fromCharCode(65 + optionIndex)}. {option}</span>
                        </label>
                      );
                    })}
                    <button type="button" onClick={() => checkAnswer(activeLevel, question, idx)} style={{ width: "fit-content", border: "none", background: "#0f172a", color: "#fff", borderRadius: 8, padding: "8px 12px", cursor: "pointer" }}>
                      Kiểm tra đáp án
                    </button>
                  </div>
                )}

                {feedback && (
                  <div style={{ marginTop: 10, padding: 10, borderRadius: 8, background: feedback.isCorrect === false ? "#fff1f2" : "#f0fdf4", color: feedback.isCorrect === false ? "#be123c" : "#166534" }}>
                    {feedback.isCorrect === false ? "❌ " : "✅ "}{feedback.message}
                  </div>
                )}
              </article>
            );
          })}
        </div>

        <div style={{ marginTop: 16, display: "flex", justifyContent: "flex-end" }}>
          <button
            type="button"
            onClick={() => navigate(`/quiz/${topicId}`)}
            style={{ border: "none", background: "#16a34a", color: "#fff", borderRadius: 10, padding: "10px 14px", cursor: "pointer" }}
          >
            Làm bài kiểm tra
          </button>
        </div>
      </main>

      <aside style={{ border: "1px solid #e5e7eb", borderRadius: 16, background: "#fff", padding: 16, height: "fit-content", position: "sticky", top: 12 }}>
        <h3 style={{ marginTop: 0 }}>Tiến độ</h3>
        <p style={{ marginBottom: 0 }}>
          {completedByLevel.easy?.done || 0}/{completedByLevel.easy?.total || 5} dễ | {" "}
          {completedByLevel.medium?.done || 0}/{completedByLevel.medium?.total || 5} trung bình | {" "}
          {completedByLevel.hard?.done || 0}/{completedByLevel.hard?.total || 5} khó
        </p>
      </aside>
    </div>
  );
}
