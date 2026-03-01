import { useEffect, useMemo, useRef, useState } from "react";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";

const bubble = {
  user: { alignSelf: "flex-end", background: "#e9edff", border: "1px solid #c9d2ff" },
  assistant: { alignSelf: "flex-start", background: "#fff", border: "1px solid #ececec" },
};

export default function Tutor() {
  const { userId } = useAuth();
  const [question, setQuestion] = useState("");
  const [topic, setTopic] = useState("");
  const [docs, setDocs] = useState([]);
  const [docId, setDocId] = useState("");
  const [messages, setMessages] = useState([]);
  const [rightSuggestions, setRightSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [learningPlan, setLearningPlan] = useState(null);
  const questionInputRef = useRef(null);

  const storageKey = useMemo(() => `tutor_conv_${userId ?? 1}_${docId || "auto"}`, [userId, docId]);

  useEffect(() => {
    (async () => {
      try {
        const data = await apiJson("/documents?limit=100&offset=0");
        const arr = data?.documents || [];
        setDocs(arr);
        if (!docId && arr.length > 0) {
          const saved = localStorage.getItem("active_document_id");
          setDocId(saved || String(arr[0].document_id));
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

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      const parsed = raw ? JSON.parse(raw) : [];
      setMessages(Array.isArray(parsed) ? parsed : []);
    } catch {
      setMessages([]);
    }
  }, [storageKey]);

  useEffect(() => {
    localStorage.setItem(storageKey, JSON.stringify(messages));
  }, [messages, storageKey]);

  const formatCitationPage = (c) => {
    const ps = c?.page_start;
    const pe = c?.page_end;
    if (Number.isInteger(ps) && Number.isInteger(pe)) return ps === pe ? `Trang ${ps}` : `Trang ${ps}–${pe}`;
    if (Number.isInteger(ps)) return `Trang ${ps}`;
    return "";
  };

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
        body: {
          user_id: userId ?? 1,
          question: q,
          topic: (topic || "").trim() || null,
          top_k: 6,
          document_ids: docId ? [Number(docId)] : null,
          allowed_topics: Array.isArray(learningPlan?.topics) ? learningPlan.topics : [],
        },
      });
      const isOffTopic = data?.is_off_topic === true || data?.off_topic === true;
      const politeOffTopic = "Mình chưa thấy nội dung này trong tài liệu lớp. Bạn thử hỏi theo đúng chương/mục…";
      const answer = isOffTopic ? politeOffTopic : (data?.answer_md || data?.answer || "(Không có câu trả lời)");
      const suggested = data?.suggested_questions || data?.follow_up_questions || [];
      setRightSuggestions(Array.isArray(suggested) ? suggested.slice(0, 5) : []);

      let meta = data || {};
      const sourceIds = Array.isArray(data?.sources)
        ? data.sources.map((x) => Number(x?.chunk_id)).filter((x) => Number.isInteger(x) && x > 0)
        : [];
      if (sourceIds.length > 0) {
        try {
          const cites = await apiJson(`/documents/chunks/citations?chunk_ids=${sourceIds.join(",")}`);
          const map = {};
          (Array.isArray(cites) ? cites : []).forEach((c) => {
            if (Number.isInteger(c?.chunk_id)) map[c.chunk_id] = c;
          });
          meta = { ...meta, citation_map: map };
        } catch {
          // ignore citation failures
        }
      }

      setMessages((prev) => [...prev, { role: "assistant", text: answer, meta, offTopic: isOffTopic }]);
    } catch (e) {
      const msg = e?.message || "Tutor lỗi";
      setError(msg);
      setMessages((prev) => [...prev, { role: "assistant", text: `❌ ${msg}`, meta: {} }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: 16, display: "grid", gridTemplateColumns: "1fr 320px", gap: 16 }}>
      <div>
        <h2>🤖 Virtual AI Tutor</h2>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
          <select value={docId} onChange={(e) => { const v = e.target.value; setDocId(v); localStorage.setItem("active_document_id", String(v)); }} style={{ padding: 10, borderRadius: 10 }}>
            <option value="">Tự động (theo topic)</option>
            {(docs || []).map((d) => <option key={d.document_id} value={d.document_id}>{d.title} (id={d.document_id})</option>)}
          </select>
          <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="(Tuỳ chọn) Topic..." style={{ padding: 10, borderRadius: 10, border: "1px solid #ddd", flex: 1 }} />
        </div>

        <div style={{ minHeight: 320, display: "flex", flexDirection: "column", gap: 10, background: "#f8f9ff", borderRadius: 12, padding: 12 }}>
          {messages.map((m, idx) => (
            <div key={idx} style={{ maxWidth: "82%", borderRadius: 14, padding: 10, ...bubble[m.role === "user" ? "user" : "assistant"] }}>
              <div style={{ fontWeight: 700, marginBottom: 4 }}>{m.role === "user" ? "Bạn" : m.offTopic ? "⚠️ Tutor" : "Tutor"}</div>
              <div style={{ whiteSpace: "pre-wrap" }}>{m.text}</div>

              {m.role === "assistant" && Array.isArray(m.meta?.sources) && m.meta.sources.length > 0 && (
                <details style={{ marginTop: 8 }}>
                  <summary>📚 Sources</summary>
                  <ul style={{ margin: "6px 0", paddingLeft: 18 }}>
                    {m.meta.sources.map((s, i) => (
                      <li key={`${s.chunk_id}-${i}`}>
                        <b>Chunk #{s.chunk_id}</b>{m.meta?.citation_map?.[s?.chunk_id] ? ` · ${formatCitationPage(m.meta.citation_map[s.chunk_id])}` : ""} (score {Number(s.score || 0).toFixed(2)}): {s.preview}
                      </li>
                    ))}
                  </ul>
                </details>
              )}

              {m.role === "assistant" && Array.isArray(m.meta?.follow_up_questions) && m.meta.follow_up_questions.length > 0 && (
                <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {m.meta.follow_up_questions.slice(0, 3).map((fq, i) => (
                    <button key={i} type="button" onClick={() => ask(fq)} style={{ borderRadius: 999, border: "1px solid #ddd", padding: "4px 10px", background: "#fff" }}>{fq}</button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        {error && <div style={{ marginTop: 10, color: "#c62828" }}>{error}</div>}

        <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
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
            style={{ padding: 10, borderRadius: 10, border: "1px solid #ddd", flex: 1 }}
          />
          <button onClick={() => ask()} disabled={loading} style={{ padding: "10px 14px" }}>{loading ? "Đang hỏi…" : "Gửi"}</button>
        </div>
      </div>

      <aside style={{ border: "1px solid #ececec", borderRadius: 12, padding: 12, height: "fit-content", background: "#fff" }}>
        <h3 style={{ marginTop: 0 }}>Panel gợi ý</h3>
        <div style={{ marginBottom: 8, color: "#666" }}>Topic hiện tại</div>
        <div style={{ fontWeight: 700, marginBottom: 12 }}>{(topic || "").trim() || "(đang theo tài liệu đã chọn)"}</div>
        <div style={{ marginBottom: 8, color: "#666" }}>Suggested questions</div>
        <div style={{ display: "grid", gap: 8 }}>
          {(rightSuggestions || []).length === 0 && <div style={{ color: "#999" }}>Chưa có gợi ý.</div>}
          {(rightSuggestions || []).map((sq, i) => (
            <button key={i} type="button" onClick={() => ask(sq)} style={{ textAlign: "left", borderRadius: 8, border: "1px solid #ddd", background: "#fafafa", padding: "8px 10px" }}>
              {sq}
            </button>
          ))}
        </div>
      </aside>
    </div>
  );
}
