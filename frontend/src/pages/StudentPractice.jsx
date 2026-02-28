import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { apiJson } from "../lib/api";

function normalizeHomeworkList(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.items)) return payload.items;
  if (Array.isArray(payload?.homeworks)) return payload.homeworks;
  if (Array.isArray(payload?.data)) return payload.data;
  return [];
}

function normalizeTopics(payload, fallbackTopicId) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.topics)) return payload.topics;
  if (Array.isArray(payload?.items)) return payload.items;
  return [
    {
      id: fallbackTopicId,
      topicId: fallbackTopicId,
      title: `Topic #${fallbackTopicId}`,
      topicTitle: `Topic #${fallbackTopicId}`,
    },
  ];
}

function getHomeworkId(item, index) {
  return String(item?.id ?? item?.homeworkId ?? item?.homework_id ?? `hw-${index}`);
}

function getQuestionId(item, index) {
  return String(item?.questionId ?? item?.question_id ?? item?.id ?? `q-${index}`);
}

function getQuestionTitle(item, index) {
  return item?.title || item?.question || item?.stem || `Bài tập ${index + 1}`;
}

function getQuestionText(item) {
  return item?.question || item?.stem || item?.content || item?.description || "(Chưa có nội dung bài tập)";
}

function getOptions(item) {
  if (Array.isArray(item?.options)) return item.options;
  if (Array.isArray(item?.choices)) return item.choices;
  return [];
}

function resolveCorrect(item) {
  return item?.correctAnswer || item?.correct_answer || item?.correctOption || item?.correct_option || "";
}

export default function StudentPractice() {
  const { topicId } = useParams();
  const userId = localStorage.getItem("user_id") || "anonymous";

  const [topics, setTopics] = useState([]);
  const [activeTopicId, setActiveTopicId] = useState(String(topicId || ""));
  const [homeworks, setHomeworks] = useState([]);
  const [activeHomeworkId, setActiveHomeworkId] = useState("");

  const [drafts, setDrafts] = useState({});
  const [submissions, setSubmissions] = useState({});
  const [hints, setHints] = useState({});
  const [hintLoadingByQuestion, setHintLoadingByQuestion] = useState({});

  const [loadingTopics, setLoadingTopics] = useState(false);
  const [loadingHomeworks, setLoadingHomeworks] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const [chatOpen, setChatOpen] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [chatSending, setChatSending] = useState(false);
  const [chatMessages, setChatMessages] = useState([]);

  const draftKey = `practice_draft_${userId}_${activeTopicId || topicId}`;

  useEffect(() => {
    async function loadTopics() {
      setLoadingTopics(true);
      try {
        const data = await apiJson(`/api/v1/learning-plan?userId=${encodeURIComponent(userId)}`);
        const topicList = normalizeTopics(data, topicId);
        setTopics(topicList);

        if (!activeTopicId && topicList.length > 0) {
          setActiveTopicId(String(topicList[0]?.id ?? topicList[0]?.topicId ?? topicId));
        }
      } catch {
        setTopics(normalizeTopics(null, topicId));
      } finally {
        setLoadingTopics(false);
      }
    }

    loadTopics();
  }, [activeTopicId, topicId, userId]);

  useEffect(() => {
    if (!activeTopicId) return;

    async function loadHomeworkByTopic() {
      setLoadingHomeworks(true);
      setError("");
      try {
        const data = await apiJson(
          `/api/v1/homework?userId=${encodeURIComponent(userId)}&topicId=${encodeURIComponent(activeTopicId)}`
        );
        const list = normalizeHomeworkList(data);
        setHomeworks(list);
        setActiveHomeworkId((prev) => prev || getHomeworkId(list[0] || {}, 0));
      } catch (e) {
        setHomeworks([]);
        setError(e?.message || "Không tải được danh sách bài tập.");
      } finally {
        setLoadingHomeworks(false);
      }
    }

    loadHomeworkByTopic();
  }, [activeTopicId, userId]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(draftKey);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        setDrafts(parsed);
      }
    } catch {
      // ignore bad local storage
    }
  }, [draftKey]);

  useEffect(() => {
    localStorage.setItem(draftKey, JSON.stringify(drafts));
  }, [draftKey, drafts]);

  const activeHomework = useMemo(
    () => homeworks.find((item, index) => getHomeworkId(item, index) === activeHomeworkId) || homeworks[0] || null,
    [activeHomeworkId, homeworks]
  );

  const activeQuestionId = useMemo(() => {
    if (!activeHomework) return "";
    return getQuestionId(activeHomework, 0);
  }, [activeHomework]);

  const completedCount = useMemo(() => {
    return homeworks.reduce((acc, item, index) => {
      const homeworkId = getHomeworkId(item, index);
      return acc + (submissions[homeworkId] ? 1 : 0);
    }, 0);
  }, [homeworks, submissions]);

  const totalCount = homeworks.length;
  const progressPct = Math.round((completedCount / Math.max(1, totalCount)) * 100);

  function updateDraft(homeworkId, value) {
    setDrafts((prev) => ({
      ...prev,
      [homeworkId]: value,
    }));
  }

  async function requestHint(item, index) {
    const questionId = getQuestionId(item, index);
    setHintLoadingByQuestion((prev) => ({ ...prev, [questionId]: true }));
    try {
      const data = await apiJson(`/api/v1/tutor/hint?questionId=${encodeURIComponent(questionId)}`);
      const hintText = data?.hint || data?.message || data?.content || "Tutor AI chưa có gợi ý cho câu này.";
      setHints((prev) => ({ ...prev, [questionId]: hintText }));
    } catch (e) {
      setHints((prev) => ({ ...prev, [questionId]: e?.message || "Không lấy được gợi ý từ Tutor AI." }));
    } finally {
      setHintLoadingByQuestion((prev) => ({ ...prev, [questionId]: false }));
    }
  }

  async function submitHomework(item, index) {
    const homeworkId = getHomeworkId(item, index);
    const questionId = getQuestionId(item, index);
    const answerText = String(drafts[homeworkId] || "").trim();

    if (!answerText) {
      setError("Bạn cần nhập câu trả lời trước khi nộp.");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      const data = await apiJson(`/api/v1/homework/${encodeURIComponent(homeworkId)}/submit`, {
        method: "POST",
        body: {
          userId,
          questionId,
          answer: answerText,
        },
      });

      const serverFeedback = data?.feedback || {};
      setSubmissions((prev) => ({
        ...prev,
        [homeworkId]: {
          submitted: true,
          correctAnswer:
            serverFeedback.correctAnswer ||
            serverFeedback.correct_answer ||
            resolveCorrect(item) ||
            "Đáp án có trong phần giải thích.",
          explanation:
            serverFeedback.explanation ||
            serverFeedback.reason ||
            item?.explanation ||
            "Hãy xem lại từng bước giải và đối chiếu với đáp án đúng.",
        },
      }));
    } catch (e) {
      setError(e?.message || "Nộp bài thất bại, vui lòng thử lại.");
    } finally {
      setSubmitting(false);
    }
  }

  function openTutorChat(item, index) {
    const questionId = getQuestionId(item, index);
    const title = getQuestionTitle(item, index);
    const content = getQuestionText(item);

    setChatOpen(true);
    setChatInput(`Giải thích giúp em câu ${title}: ${content}`);
    setChatMessages((prev) => {
      if (prev.length > 0) return prev;
      return [
        {
          role: "system",
          text: `Context hiện tại: questionId=${questionId}. Học sinh đang luyện tập, không phải thi có timer.`,
        },
      ];
    });
  }

  async function sendTutorMessage() {
    const question = chatInput.trim();
    if (!question || !activeHomework) return;

    const studentMessage = { role: "user", text: question };
    setChatMessages((prev) => [...prev, studentMessage]);
    setChatInput("");
    setChatSending(true);

    try {
      const data = await apiJson("/api/v1/tutor/chat", {
        method: "POST",
        body: {
          user_id: Number(userId) || 0,
          question,
          topic: activeTopicId,
        },
      });

      const tutorAnswer =
        data?.answer ||
        data?.message ||
        data?.content ||
        "Tutor AI đã nhận câu hỏi của bạn nhưng chưa tạo được phản hồi chi tiết.";

      setChatMessages((prev) => [...prev, { role: "assistant", text: tutorAnswer }]);
    } catch (e) {
      setChatMessages((prev) => [...prev, { role: "assistant", text: e?.message || "Tutor AI tạm thời không phản hồi." }]);
    } finally {
      setChatSending(false);
    }
  }

  return (
    <div style={{ maxWidth: 1240, margin: "0 auto", padding: 16, display: "grid", gridTemplateColumns: "300px 1fr", gap: 16 }}>
      <aside style={{ border: "1px solid #e2e8f0", borderRadius: 14, background: "#fff", padding: 14, alignSelf: "start", position: "sticky", top: 12 }}>
        <h2 style={{ margin: "0 0 10px" }}>Bài tập theo chủ đề</h2>
        <p style={{ margin: "0 0 10px", color: "#475569", fontSize: 13 }}>
          Điểm bài tập chỉ để luyện tập, không tính vào điểm cuối kỳ.
        </p>

        <div style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: "#334155", marginBottom: 5 }}>
            <span>Tiến độ</span>
            <strong>{completedCount}/{totalCount}</strong>
          </div>
          <div style={{ height: 8, borderRadius: 999, background: "#e2e8f0", overflow: "hidden" }}>
            <div style={{ width: `${progressPct}%`, height: "100%", background: "#2563eb" }} />
          </div>
        </div>

        {loadingTopics && <p style={{ color: "#64748b" }}>Đang tải danh sách topic...</p>}

        <div style={{ display: "grid", gap: 8, marginBottom: 10 }}>
          {topics.map((topic, index) => {
            const id = String(topic?.id ?? topic?.topicId ?? `topic-${index}`);
            const active = id === activeTopicId;
            return (
              <button
                key={id}
                type="button"
                onClick={() => setActiveTopicId(id)}
                style={{
                  border: active ? "1px solid #2563eb" : "1px solid #e2e8f0",
                  borderRadius: 10,
                  padding: "8px 10px",
                  background: active ? "#eff6ff" : "#fff",
                  textAlign: "left",
                  cursor: "pointer",
                  fontWeight: 600,
                }}
              >
                {topic?.title || topic?.topicTitle || `Topic ${index + 1}`}
              </button>
            );
          })}
        </div>

        <h3 style={{ marginBottom: 8 }}>Danh sách bài tập</h3>
        {loadingHomeworks && <p style={{ color: "#64748b" }}>Đang tải bài tập...</p>}
        <div style={{ display: "grid", gap: 8 }}>
          {homeworks.map((item, index) => {
            const hwId = getHomeworkId(item, index);
            const active = hwId === activeHomeworkId;
            const done = Boolean(submissions[hwId]);

            return (
              <button
                key={hwId}
                type="button"
                onClick={() => setActiveHomeworkId(hwId)}
                style={{
                  border: active ? "1px solid #1d4ed8" : "1px solid #e2e8f0",
                  borderRadius: 10,
                  padding: "10px",
                  background: active ? "#dbeafe" : "#f8fafc",
                  textAlign: "left",
                  cursor: "pointer",
                }}
              >
                <div style={{ fontWeight: 700 }}>{getQuestionTitle(item, index)}</div>
                {done && (
                  <span style={{ marginTop: 6, display: "inline-block", background: "#dcfce7", color: "#166534", fontSize: 12, padding: "2px 8px", borderRadius: 999 }}>
                    Hoàn thành
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </aside>

      <main style={{ border: "1px solid #e2e8f0", borderRadius: 14, background: "#fff", padding: 16, minHeight: 520, position: "relative" }}>
        {error && <p style={{ color: "#b91c1c", marginTop: 0 }}>{error}</p>}

        {!activeHomework && !loadingHomeworks && <p>Chưa có bài tập trong topic này.</p>}

        {activeHomework && (
          <div>
            <h2 style={{ marginTop: 0 }}>{getQuestionTitle(activeHomework, 0)}</h2>
            <p style={{ whiteSpace: "pre-wrap", color: "#0f172a" }}>{getQuestionText(activeHomework)}</p>

            {getOptions(activeHomework).length > 0 && (
              <ul style={{ paddingLeft: 20 }}>
                {getOptions(activeHomework).map((opt, idx) => (
                  <li key={`opt-${idx}`} style={{ marginBottom: 4 }}>
                    {String.fromCharCode(65 + idx)}. {String(opt)}
                  </li>
                ))}
              </ul>
            )}

            <label style={{ fontWeight: 600, display: "block", marginBottom: 6 }}>Câu trả lời của bạn</label>
            <textarea
              rows={5}
              value={drafts[getHomeworkId(activeHomework, 0)] || ""}
              onChange={(event) => updateDraft(getHomeworkId(activeHomework, 0), event.target.value)}
              placeholder="Nhập câu trả lời... draft sẽ tự lưu khi bạn refresh"
              style={{ width: "100%", border: "1px solid #cbd5e1", borderRadius: 10, padding: 10 }}
            />

            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 12 }}>
              <button
                type="button"
                onClick={() => requestHint(activeHomework, 0)}
                disabled={hintLoadingByQuestion[activeQuestionId]}
                style={{ border: "none", borderRadius: 8, padding: "9px 12px", background: "#0f172a", color: "#fff", cursor: "pointer" }}
              >
                {hintLoadingByQuestion[activeQuestionId] ? "Đang xin gợi ý..." : "Xem AI Hint"}
              </button>

              <button
                type="button"
                onClick={() => openTutorChat(activeHomework, 0)}
                style={{ border: "1px solid #cbd5e1", borderRadius: 8, padding: "9px 12px", background: "#fff", cursor: "pointer" }}
              >
                Hỏi Tutor AI
              </button>

              <button
                type="button"
                onClick={() => submitHomework(activeHomework, 0)}
                disabled={submitting}
                style={{ border: "none", borderRadius: 8, padding: "9px 12px", background: "#2563eb", color: "#fff", cursor: "pointer" }}
              >
                {submitting ? "Đang nộp..." : "Nộp bài tập"}
              </button>
            </div>

            {hints[activeQuestionId] && (
              <section style={{ marginTop: 14, border: "1px solid #e2e8f0", borderRadius: 10, background: "#f8fafc", padding: 12 }}>
                <strong>AI Hint:</strong>
                <p style={{ marginBottom: 0, whiteSpace: "pre-wrap" }}>{hints[activeQuestionId]}</p>
              </section>
            )}

            {submissions[getHomeworkId(activeHomework, 0)] && (
              <section style={{ marginTop: 14, border: "1px solid #bbf7d0", borderRadius: 10, background: "#f0fdf4", padding: 12 }}>
                <strong>Đáp án & giải thích sau khi nộp:</strong>
                <p style={{ margin: "8px 0 4px" }}>
                  <b>Đáp án đúng:</b> {submissions[getHomeworkId(activeHomework, 0)]?.correctAnswer}
                </p>
                <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                  <b>Giải thích:</b> {submissions[getHomeworkId(activeHomework, 0)]?.explanation}
                </p>
              </section>
            )}
          </div>
        )}

        {chatOpen && (
          <aside style={{ position: "absolute", top: 0, right: 0, width: 360, height: "100%", borderLeft: "1px solid #e2e8f0", background: "#ffffff", padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <strong>Chat với Tutor AI</strong>
              <button type="button" onClick={() => setChatOpen(false)} style={{ border: "none", background: "transparent", cursor: "pointer" }}>✕</button>
            </div>

            <div style={{ fontSize: 12, color: "#475569" }}>
              Context: câu hỏi hiện tại trong bài tập luyện tập (không có timer).
            </div>

            <div style={{ flex: 1, overflowY: "auto", border: "1px solid #e2e8f0", borderRadius: 8, padding: 8, background: "#f8fafc" }}>
              {chatMessages.map((msg, index) => (
                <div key={`msg-${index}`} style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 12, color: "#334155", textTransform: "capitalize" }}>{msg.role}</div>
                  <div style={{ whiteSpace: "pre-wrap" }}>{msg.text}</div>
                </div>
              ))}
            </div>

            <textarea
              rows={3}
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              placeholder="Nhập câu hỏi cho Tutor AI..."
              style={{ width: "100%", border: "1px solid #cbd5e1", borderRadius: 8, padding: 8 }}
            />
            <button
              type="button"
              onClick={sendTutorMessage}
              disabled={chatSending}
              style={{ border: "none", borderRadius: 8, padding: "8px 12px", background: "#0f172a", color: "white", cursor: "pointer" }}
            >
              {chatSending ? "Đang gửi..." : "Gửi cho Tutor"}
            </button>
          </aside>
        )}
      </main>
    </div>
  );
}
