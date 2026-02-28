import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";

function getHomeworkId(item, index) {
  return Number(item?.id ?? item?.homework_id ?? index + 1);
}

export default function StudentPractice() {
  const { topicId } = useParams();
  const navigate = useNavigate();
  const { userId } = useAuth();

  const [topicName, setTopicName] = useState(`Topic ${topicId}`);
  const [homeworkList, setHomeworkList] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState({});
  const [completedIds, setCompletedIds] = useState(new Set());
  const [hintUsedById, setHintUsedById] = useState({});
  const [showHint, setShowHint] = useState(false);
  const [hintContent, setHintContent] = useState("");
  const [showExplanation, setShowExplanation] = useState(false);
  const [resultById, setResultById] = useState({});
  const [loading, setLoading] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [error, setError] = useState("");

  const currentQuestion = homeworkList[currentIndex] || null;
  const total = homeworkList.length;
  const doneCount = completedIds.size;
  const doneAll = total > 0 && doneCount === total;

  useEffect(() => {
    async function loadHomework() {
      if (!topicId) return;
      setLoading(true);
      setError("");
      try {
        let data = await apiJson(`/v1/homework?topicId=${topicId}&userId=${userId}`);
        let items = Array.isArray(data?.items) ? data.items : [];

        if (items.length === 0) {
          await apiJson(`/v1/homework/generate?topicId=${topicId}&userId=${userId}`, { method: "POST" });
          data = await apiJson(`/v1/homework?topicId=${topicId}&userId=${userId}`);
          items = Array.isArray(data?.items) ? data.items : [];
        }

        setTopicName(data?.topic || `Topic ${topicId}`);
        setHomeworkList(items);
        setCurrentIndex(0);
      } catch (e) {
        setError(e?.message || "Không tải được bài tập.");
      } finally {
        setLoading(false);
      }
    }

    loadHomework();
  }, [topicId, userId]);

  useEffect(() => {
    if (!currentQuestion) return;
    setShowHint(false);
    setHintContent("");
    setShowExplanation(false);
  }, [currentIndex, currentQuestion]);

  const progressLabel = useMemo(() => `${doneCount}/${total}`, [doneCount, total]);

  async function onAskHint() {
    if (!currentQuestion) return;
    setShowHint(true);
    try {
      const data = await apiJson("/v1/tutor/chat", {
        method: "POST",
        body: {
          user_id: Number(userId),
          question: `Cho tôi gợi ý (KHÔNG đáp án) cho câu: ${currentQuestion.stem}`,
          topic: topicName,
        },
      });
      setHintContent(data?.answer || "Tutor đang bận, hãy thử hỏi lại.");
      setHintUsedById((prev) => ({ ...prev, [getHomeworkId(currentQuestion, currentIndex)]: true }));
    } catch (e) {
      setHintContent(e?.message || "Không lấy được gợi ý AI.");
    }
  }

  async function onSubmitQuestion() {
    if (!currentQuestion) return;
    const homeworkId = getHomeworkId(currentQuestion, currentIndex);
    const answer = answers[homeworkId];
    if (answer === undefined || String(answer).trim() === "") {
      setError("Vui lòng nhập/chọn đáp án trước khi nộp.");
      return;
    }

    setError("");
    try {
      const data = await apiJson(`/v1/homework/${topicId}/answer`, {
        method: "POST",
        body: {
          question_id: Number(currentQuestion.questionId || homeworkId),
          answer,
          used_hint: Boolean(hintUsedById[homeworkId]),
        },
      });
      setResultById((prev) => ({ ...prev, [homeworkId]: data }));
      setCompletedIds((prev) => new Set([...prev, homeworkId]));
      setShowExplanation(true);
    } catch (e) {
      setError(e?.message || "Nộp câu trả lời thất bại.");
    }
  }

  async function sendTutorChat() {
    const q = chatInput.trim();
    if (!q) return;
    setChatMessages((prev) => [...prev, { role: "user", text: q }]);
    setChatInput("");
    setChatLoading(true);
    try {
      const data = await apiJson("/v1/tutor/chat", {
        method: "POST",
        body: { user_id: Number(userId), question: q, topic: topicName },
      });
      setChatMessages((prev) => [...prev, { role: "assistant", text: data?.answer || "Tutor chưa phản hồi." }]);
    } catch (e) {
      setChatMessages((prev) => [...prev, { role: "assistant", text: e?.message || "Tutor lỗi." }]);
    } finally {
      setChatLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 1280, margin: "0 auto", padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Bài Tập: {topicName}</h2>
        <div style={{ fontWeight: 700 }}>Progress: {progressLabel} ✅</div>
      </div>

      {loading && <p>Đang tải bài tập...</p>}
      {!loading && total === 0 && <p>Chưa có bài tập cho topic này. AI đang tạo...</p>}
      {!!error && <p style={{ color: "#b91c1c" }}>{error}</p>}

      {!!total && (
        <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 16 }}>
          <aside style={{ border: "1px solid #e2e8f0", borderRadius: 12, padding: 12 }}>
            {homeworkList.map((item, idx) => {
              const id = getHomeworkId(item, idx);
              const isDone = completedIds.has(id);
              const isCurrent = idx === currentIndex;
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => setCurrentIndex(idx)}
                  style={{ width: "100%", marginBottom: 8, textAlign: "left", borderRadius: 8, padding: "8px 10px", border: isCurrent ? "1px solid #2563eb" : "1px solid #e2e8f0", background: isCurrent ? "#eff6ff" : "#fff" }}
                >
                  {isDone ? "●" : isCurrent ? "🔵" : "○"} Câu {idx + 1} {isDone ? "✅" : ""}
                </button>
              );
            })}
          </aside>

          <main style={{ border: "1px solid #e2e8f0", borderRadius: 12, padding: 16, position: "relative" }}>
            <h3 style={{ marginTop: 0 }}>Câu {currentIndex + 1}: {currentQuestion?.stem}</h3>
            {Array.isArray(currentQuestion?.options) && currentQuestion.options.length > 0 ? (
              <div style={{ display: "grid", gap: 8 }}>
                {currentQuestion.options.map((opt, idx) => {
                  const id = getHomeworkId(currentQuestion, currentIndex);
                  return (
                    <label key={idx} style={{ display: "flex", gap: 8 }}>
                      <input type="radio" name={`q-${id}`} checked={String(answers[id] ?? "") === String(idx)} onChange={() => setAnswers((prev) => ({ ...prev, [id]: String(idx) }))} />
                      <span>{opt}</span>
                    </label>
                  );
                })}
              </div>
            ) : (
              <textarea
                rows={6}
                value={answers[getHomeworkId(currentQuestion, currentIndex)] || ""}
                onChange={(e) => setAnswers((prev) => ({ ...prev, [getHomeworkId(currentQuestion, currentIndex)]: e.target.value }))}
                style={{ width: "100%", border: "1px solid #cbd5e1", borderRadius: 10, padding: 10 }}
              />
            )}

            <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button type="button" onClick={onAskHint}>💡 Xem gợi ý AI</button>
              <button type="button" onClick={onSubmitQuestion}>📤 Nộp câu này</button>
              <button
                type="button"
                onClick={() => {
                  setChatOpen(true);
                  setChatInput(`Giải thích thêm cho câu ${currentIndex + 1}: ${currentQuestion?.stem || ""}`);
                }}
              >
                Hỏi Tutor AI
              </button>
            </div>

            {showHint && !!hintContent && (
              <div style={{ marginTop: 12, background: "#fef9c3", border: "1px solid #fde68a", borderRadius: 10, padding: 10 }}>
                <b>Gợi ý AI:</b> {hintContent}
              </div>
            )}

            {showExplanation && resultById[getHomeworkId(currentQuestion, currentIndex)] && (
              <div style={{ marginTop: 12, borderRadius: 10, padding: 10, border: resultById[getHomeworkId(currentQuestion, currentIndex)]?.is_correct ? "1px solid #86efac" : "1px solid #fca5a5", background: resultById[getHomeworkId(currentQuestion, currentIndex)]?.is_correct ? "#f0fdf4" : "#fef2f2" }}>
                <b>{resultById[getHomeworkId(currentQuestion, currentIndex)]?.is_correct ? "✅ Chính xác!" : `❌ Chưa đúng. Đáp án: ${resultById[getHomeworkId(currentQuestion, currentIndex)]?.correct_answer}`}</b>
                <p style={{ marginBottom: 0 }}>{resultById[getHomeworkId(currentQuestion, currentIndex)]?.explanation}</p>
              </div>
            )}

            <div style={{ marginTop: 16, display: "flex", justifyContent: "space-between" }}>
              <button type="button" disabled={currentIndex === 0} onClick={() => setCurrentIndex((v) => Math.max(0, v - 1))}>← Trước</button>
              <button type="button" disabled={currentIndex >= total - 1} onClick={() => setCurrentIndex((v) => Math.min(total - 1, v + 1))}>Tiếp theo →</button>
            </div>

            {doneAll && (
              <div style={{ marginTop: 16, border: "1px solid #86efac", background: "#f0fdf4", borderRadius: 10, padding: 12 }}>
                🎉 🎊 Xuất sắc! Bạn đã hoàn thành bài tập topic này.
                <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
                  <button type="button" onClick={() => navigate("/learning-path")}>Quay lại lộ trình học</button>
                  <button type="button" onClick={() => navigate("/learning-path")}>Làm bài tập topic tiếp theo →</button>
                </div>
              </div>
            )}

            {chatOpen && (
              <aside style={{ position: "absolute", top: 0, right: 0, width: 400, height: "100%", borderLeft: "1px solid #e2e8f0", background: "#fff", padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <strong>Tutor AI</strong>
                  <button type="button" onClick={() => setChatOpen(false)}>✕</button>
                </div>
                <small>Context: Câu {currentIndex + 1} - {currentQuestion?.stem}</small>
                <div style={{ flex: 1, overflow: "auto", border: "1px solid #e2e8f0", borderRadius: 8, padding: 8 }}>
                  {chatMessages.map((m, i) => (
                    <div key={i}><b>{m.role}:</b> {m.text}</div>
                  ))}
                </div>
                <textarea rows={3} value={chatInput} onChange={(e) => setChatInput(e.target.value)} />
                <button type="button" onClick={sendTutorChat} disabled={chatLoading}>{chatLoading ? "Đang gửi..." : "Gửi"}</button>
              </aside>
            )}
          </main>
        </div>
      )}
    </div>
  );
}
