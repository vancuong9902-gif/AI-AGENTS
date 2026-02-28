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
  const questionInputRef = useRef(null);

  const selectedDoc = (docs || []).find((d) => String(d.document_id) === String(docId));
  const currentTopic = (topic || "").trim() || selectedDoc?.title || "tài liệu hiện tại";

  // Load teacher documents so the student can scope Tutor to the right materials.
  useEffect(() => {
    (async () => {
      try {
        const data = await apiJson("/documents");
        const arr = data?.documents || [];
        setDocs(arr);
        // default to most recent document (optional)
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

  const ask = async () => {
    const q = (question || "").trim();
    if (!q) return;
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
        <button onClick={ask} disabled={loading} style={{ padding: "10px 14px" }}>
          {loading ? "Đang hỏi…" : "Gửi"}
        </button>
      </div>
      <div style={{ marginTop: 8, color: "#6c757d", fontSize: 14 }}>💡 Chỉ hỏi về nội dung trong tài liệu: {currentTopic}</div>

      {error && (
        <div style={{ marginTop: 12, background: "#fff3f3", border: "1px solid #ffd0d0", padding: 12, borderRadius: 12 }}>
          {error}
        </div>
      )}

      <div style={{ marginTop: 16, display: "grid", gap: 12 }}>
        {messages.map((m, idx) => {
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
                background: m.role === "user" ? "#f7f7ff" : "#fff",
                borderRadius: 12,
                padding: 12,
                boxShadow: "0 2px 10px rgba(0,0,0,0.06)",
              }}
            >
            <div style={{ fontWeight: 900, marginBottom: 6 }}>{m.role === "user" ? "Bạn" : "Tutor"}</div>
            <pre style={{ whiteSpace: "pre-wrap", margin: 0, fontFamily: "inherit" }}>{m.text}</pre>

            {m.role === "assistant" && m.meta?.sources?.length > 0 && (
              <details style={{ marginTop: 10 }}>
                <summary style={{ cursor: "pointer" }}>Nguồn (chunks)</summary>
                <div style={{ display: "grid", gap: 10, marginTop: 8 }}>
                  {m.meta.sources.slice(0, 6).map((s) => (
                    <div key={s.chunk_id} style={{ border: "1px solid #eee", borderRadius: 10, padding: 10 }}>
                      <div style={{ fontWeight: 800 }}>
                        {s.document_title || `Doc ${s.document_id ?? ""}`} • chunk {s.chunk_id}
                      </div>
                      <div style={{ color: "#666", marginTop: 4 }}>{s.preview}</div>
                    </div>
                  ))}
                </div>
              </details>
            )}

            {m.role === "assistant" && m.meta?.follow_up_questions?.length > 0 && (
              <div style={{ marginTop: 10 }}>
                <div style={{ fontWeight: 900 }}>Gợi ý hỏi thêm</div>
                <ul style={{ marginTop: 6 }}>
                  {m.meta.follow_up_questions.map((q, i) => (
                    <li key={i}>{q}</li>
                  ))}
                </ul>
              </div>
            )}

            {m.role === "assistant" && m.meta?.quick_check_mcq?.length > 0 && (
              <div style={{ marginTop: 10 }}>
                <div style={{ fontWeight: 900 }}>Tự kiểm tra nhanh</div>
                {m.meta.quick_check_mcq.map((q, i) => (
                  <div key={i} style={{ marginTop: 8, border: "1px solid #eee", borderRadius: 10, padding: 10 }}>
                    <div style={{ fontWeight: 800 }}>{q.stem}</div>
                    <ol style={{ marginTop: 6 }}>
                      {(q.options || []).map((op, j) => (
                        <li key={j}>{op}</li>
                      ))}
                    </ol>
                    <div style={{ color: "#666" }}>
                      Đáp án: <b>{(q.correct_index ?? -1) + 1}</b>
                      {q.explanation ? ` • ${q.explanation}` : ""}
                    </div>
                  </div>
                ))}
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
