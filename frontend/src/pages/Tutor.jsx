import { useEffect, useRef, useState } from "react";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";

export default function Tutor() {
  const { userId } = useAuth();
  const [question, setQuestion] = useState("");
  const [topic, setTopic] = useState("");
  const [docs, setDocs] = useState([]);
  const [docId, setDocId] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [learningPlan, setLearningPlan] = useState(null);
  const questionInputRef = useRef(null);

  const selectedDoc = (docs || []).find((d) => String(d.document_id) === String(docId));
  const currentTopic = (topic || "").trim() || selectedDoc?.title || "tài liệu hiện tại";

  useEffect(() => {
    (async () => {
      try {
        const data = await apiJson("/documents");
        const arr = data?.documents || [];
        setDocs(arr);
        if (!docId && Array.isArray(arr) && arr.length > 0) {
          const saved = localStorage.getItem("active_document_id");
          if (saved) setDocId(saved);
          else setDocId(String(arr[0].document_id));
        }
      } catch {
        // ignore
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);


  useEffect(() => {
    (async () => {
      try {
        const data = await apiJson(`/lms/student/${userId ?? 1}/my-path`);
        setLearningPlan(data || null);
      } catch {
        // ignore
      }
    })();
  }, [userId]);

  const ask = async (overrideQuestion) => {
    const q = ((overrideQuestion ?? question) || "").trim();
    if (!q || loading) return;
    setError("");
    setLoading(true);
    setMessages((prev) => [...prev, { role: "user", text: q }]);
    setQuestion("");
    try {
      const data = await apiJson("/tutor/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId ?? 1,
          question: q,
          topic: (topic || "").trim() || null,
          top_k: 6,
          document_ids: docId ? [Number(docId)] : null,
          allowed_topics: Array.isArray(learningPlan?.topics) ? learningPlan.topics : [],
        }),
      });

      const answer = data?.answer || data?.answer_md || "(Không có câu trả lời)";
      const isOffTopic = data?.is_off_topic === true || data?.off_topic === true;
      setMessages((prev) => [...prev, { role: "assistant", text: answer, meta: data, offTopic: isOffTopic }]);
    } catch (e) {
      const msg = e?.message || "Tutor lỗi";
      const sug = e?.details?.suggestion || e?.details?.details?.suggestion || null;
      const full = sug ? `${msg}\n\n👉 ${sug}` : msg;
      setError(full);
      setMessages((prev) => [...prev, { role: "assistant", text: `❌ ${full}` }]);
    } finally {
      setLoading(false);
    }
  };

  const confidenceText = (value) => {
    const c = Number(value ?? 0.8);
    if (c >= 0.8) return "";
    if (c >= 0.5) return "Thông tin này có thể cần xác minh thêm";
    return "Tôi không chắc chắn, vui lòng tham khảo tài liệu gốc";
  };

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: 16 }}>
      <h2>🤖 Virtual AI Tutor</h2>
      <p style={{ color: "#555", marginTop: 0 }}>
        Học sinh dùng Tutor để <b>hỏi - đáp</b> dựa trên tài liệu giáo viên đã upload. Nếu tài liệu OCR lỗi/rời rạc, Tutor sẽ yêu cầu upload bản sạch.
      </p>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <select
          value={docId}
          onChange={(e) => {
            const v = e.target.value;
            setDocId(v);
            if (v) localStorage.setItem("active_document_id", String(v));
          }}
          title="Chọn tài liệu để Tutor trả lời đúng ngữ liệu"
          style={{ padding: 10, borderRadius: 10, border: "1px solid #ddd", flex: "0 0 260px" }}
        >
          <option value="">Tự động (theo topic)</option>
          {(docs || []).map((d) => (
            <option key={d.document_id} value={d.document_id}>
              {d.title} (id={d.document_id})
            </option>
          ))}
        </select>

        <input
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="(Tuỳ chọn) Topic..."
          style={{ padding: 10, borderRadius: 10, border: "1px solid #ddd", flex: "0 0 220px" }}
        />
        <input
          ref={questionInputRef}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask();
            }
          }}
          placeholder="Nhập câu hỏi..."
          style={{ padding: 10, borderRadius: 10, border: "1px solid #ddd", flex: "1 1 420px" }}
        />
        <button onClick={() => ask()} disabled={loading} style={{ padding: "10px 14px" }}>
          {loading ? "Đang hỏi…" : "Gửi"}
        </button>
      </div>
      <div style={{ marginTop: 10 }}>
        <span style={{ background: "#e8f5e9", color: "#2e7d32", padding: "6px 10px", borderRadius: 999, fontSize: 13, fontWeight: 700 }}>
          🎯 Đang học: {currentTopic}
        </span>
      </div>

      {error && (
        <div style={{ marginTop: 12, background: "#fff3f3", border: "1px solid #ffd0d0", padding: 12, borderRadius: 12 }}>
          {error}
        </div>
      )}

      <div style={{ marginTop: 16, display: "grid", gap: 12 }}>
        {messages.map((m, idx) => {
          const warn = m.role === "assistant" && m.offTopic;
          const confidenceMsg = m.role === "assistant" ? confidenceText(m.meta?.confidence) : "";
          if (m.role === "assistant" && m.offTopic) {
            const topicScope = m.meta?.topic_scope || currentTopic;
            const redirectHint = m.meta?.redirect_hint || `Mình muốn hỏi về ${topicScope}`;
            const followUps = Array.isArray(m.meta?.follow_up_questions) ? m.meta.follow_up_questions.slice(0, 3) : [];

            return (
              <div
                key={idx}
                style={{
                  position: "relative",
                  background: "#fff3cd",
                  border: "1px solid #f0c75e",
                  padding: 12,
                  borderRadius: 10,
                  margin: "8px 0",
                }}
              >
                <div style={{ position: "absolute", top: 8, right: 10, fontSize: 18 }}>⚠️</div>
                <div style={{ fontWeight: 900, marginBottom: 6 }}>Câu hỏi ngoài phạm vi</div>
                <div style={{ whiteSpace: "pre-wrap" }}>{m.text}</div>
                {followUps.length > 0 && (
                  <div style={{ marginTop: 10 }}>
                    <div style={{ fontWeight: 800, marginBottom: 8 }}>Thay vào đó, bạn có muốn hỏi về:</div>
                    <div style={{ display: "grid", gap: 8 }}>
                      {followUps.map((fq, i) => (
                        <button
                          key={i}
                          type="button"
                          onClick={() => {
                            setQuestion(fq);
                            questionInputRef.current?.focus();
                          }}
                          style={{
                            textAlign: "left",
                            borderRadius: 8,
                            border: "1px solid #f0c75e",
                            background: "#fff9e8",
                            padding: "8px 10px",
                            cursor: "pointer",
                          }}
                        >
                          {fq}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                <div style={{ marginTop: 10 }}>
                  <button
                    type="button"
                    onClick={() => {
                      setQuestion(redirectHint);
                      questionInputRef.current?.focus();
                    }}
                    style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid #e0b000", background: "#fff" }}
                  >
                    Hỏi về {topicScope}
                  </button>
                </div>
              </div>
            );
          }
          return (
            <div
              key={idx}
              style={{
                background: warn ? "#fff8db" : m.role === "user" ? "#f7f7ff" : "#fff",
                borderRadius: 12,
                padding: 12,
                boxShadow: "0 2px 10px rgba(0,0,0,0.06)",
                border: warn ? "1px solid #ffdf80" : "none",
              }}
            >
              <div style={{ fontWeight: 900, marginBottom: 6 }}>{m.role === "user" ? "Bạn" : warn ? "⚠️ Tutor" : "Tutor"}</div>
              <pre style={{ whiteSpace: "pre-wrap", margin: 0, fontFamily: "inherit" }}>{m.text}</pre>

              {m.role === "assistant" && m.meta?.sources_used?.length > 0 && (
                <div style={{ marginTop: 8, color: "#777", fontSize: 13 }}>📚 Dựa trên: {m.meta.sources_used.join(", ")}</div>
              )}

              {confidenceMsg && <div style={{ marginTop: 8, color: "#9c6b00", fontSize: 13 }}>{confidenceMsg}</div>}

              {m.role === "assistant" && m.meta?.follow_up_questions?.length > 0 && (
                <div style={{ marginTop: 10 }}>
                  <div style={{ fontWeight: 900, marginBottom: 6 }}>Gợi ý hỏi thêm</div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {m.meta.follow_up_questions.map((q, i) => (
                      <button
                        key={i}
                        type="button"
                        onClick={() => ask(q)}
                        style={{ borderRadius: 999, border: "1px solid #d6d6d6", background: "#fafafa", padding: "6px 10px", cursor: "pointer" }}
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {messages.length === 0 && <div style={{ color: "#666" }}>Chưa có hội thoại. Hãy hỏi 1 câu.</div>}
      </div>
    </div>
  );
}
