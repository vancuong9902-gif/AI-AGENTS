import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { apiJson } from "../lib/api";

const TABS = [
  { key: "theory", label: "Lý thuyết" },
  { key: "exercises", label: "Bài tập" },
  { key: "quiz", label: "Mini Quiz" },
];

function MarkdownSafe({ text }) {
  if (!String(text || "").trim()) {
    return <p className="text-slate-500">Chưa có nội dung lý thuyết.</p>;
  }

  return (
    <div className="space-y-2 text-slate-700">
      {String(text)
        .split(/\r?\n/)
        .map((line, index) => {
          const value = line.trim();
          if (!value) return <div key={index} className="h-2" />;
          if (value.startsWith("### ")) return <h4 key={index} className="text-base font-semibold">{value.replace(/^###\s+/, "")}</h4>;
          if (value.startsWith("## ")) return <h3 key={index} className="text-lg font-semibold">{value.replace(/^##\s+/, "")}</h3>;
          if (value.startsWith("# ")) return <h2 key={index} className="text-xl font-bold">{value.replace(/^#\s+/, "")}</h2>;
          if (value.startsWith("- ")) return <li key={index} className="ml-6 list-disc">{value.replace(/^-\s+/, "")}</li>;
          return <p key={index}>{line}</p>;
        })}
    </div>
  );
}

function asArray(v) {
  return Array.isArray(v) ? v : [];
}

function ExerciseCard({ item, chunksById }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-slate-200 p-4">
      <p className="font-semibold text-slate-800">{item?.question}</p>
      {asArray(item?.options).length > 0 && (
        <ul className="mt-2 list-disc pl-6 text-sm text-slate-700">
          {asArray(item?.options).map((opt, idx) => <li key={idx}>{opt}</li>)}
        </ul>
      )}
      <button type="button" onClick={() => setOpen((v) => !v)} className="mt-3 rounded-lg bg-slate-100 px-3 py-1 text-sm font-medium">
        {open ? "Ẩn đáp án" : "Xem đáp án"}
      </button>
      {open && (
        <div className="mt-3 space-y-2 text-sm text-slate-700">
          <p><b>Đáp án:</b> {item?.answer || "N/A"}</p>
          <p><b>Giải thích:</b> {item?.explanation || "N/A"}</p>
          <p><b>Trích nguồn:</b> {asArray(item?.source_chunks).join(", ") || "N/A"}</p>
          <div className="space-y-2">
            {asArray(item?.source_chunks).map((cid) => (
              <blockquote key={cid} className="rounded border-l-4 border-blue-400 bg-blue-50 p-2 text-xs text-slate-700">
                [chunk:{cid}] {chunksById?.[cid] || "(Không có preview)"}
              </blockquote>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function TopicDetail() {
  const { documentId, topicId } = useParams();
  const [tab, setTab] = useState("theory");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [topic, setTopic] = useState(null);
  const [quizAnswers, setQuizAnswers] = useState({});
  const [quizResult, setQuizResult] = useState(null);
  const [timeLeft, setTimeLeft] = useState(180);

  const fetchTopic = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await apiJson(`/documents/${documentId}/topics/${topicId}?include_content=1&include_material=1`);
      setTopic(data || null);
      setTimeLeft(180);
      setQuizAnswers({});
      setQuizResult(null);
    } catch (e) {
      setError(e?.message || "Không thể tải topic");
    } finally {
      setLoading(false);
    }
  }, [documentId, topicId]);

  useEffect(() => {
    fetchTopic();
  }, [fetchTopic]);

  useEffect(() => {
    if (tab !== "quiz" || quizResult) return undefined;
    if (timeLeft <= 0) return undefined;
    const timer = setTimeout(() => setTimeLeft((v) => v - 1), 1000);
    return () => clearTimeout(timer);
  }, [tab, quizResult, timeLeft]);

  const material = topic?.material || {};
  const exercises = material?.exercises || { easy: [], medium: [], hard: [] };
  const miniQuiz = asArray(material?.mini_quiz).slice(0, 5);

  const chunksById = useMemo(() => {
    const out = {};
    asArray(topic?.chunk_previews).forEach((c) => {
      out[c?.chunk_id] = c?.text_preview;
    });
    return out;
  }, [topic?.chunk_previews]);

  const onGradeQuiz = useCallback(() => {
    let correct = 0;
    miniQuiz.forEach((q, idx) => {
      const selected = Number(quizAnswers[idx]);
      const answerText = String(q?.answer || "").trim().toLowerCase();
      const selectedText = Number.isInteger(selected) ? String(q?.options?.[selected] || "").trim().toLowerCase() : "";
      if (selectedText && answerText && selectedText === answerText) correct += 1;
    });
    setQuizResult({ correct, total: miniQuiz.length, score: miniQuiz.length ? Math.round((correct / miniQuiz.length) * 100) : 0 });
  }, [miniQuiz, quizAnswers]);

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900">{topic?.display_title || topic?.title || "Topic Detail"}</h1>
        <p className="mt-2 text-sm text-slate-500">Document #{documentId} • Topic #{topicId}</p>
        {topic?.material_warning && <p className="mt-2 text-sm text-amber-600">Cảnh báo: {asArray(topic.material_warning).join("; ")}</p>}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex gap-2 border-b border-slate-200 pb-3">
          {TABS.map((item) => (
            <button key={item.key} type="button" onClick={() => setTab(item.key)} className={`rounded-lg px-4 py-2 text-sm font-medium ${tab === item.key ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"}`}>
              {item.label}
            </button>
          ))}
        </div>

        {loading && <p className="mt-4 text-slate-500">Đang tải...</p>}
        {error && <p className="mt-4 text-red-600">{error}</p>}

        {!loading && !error && tab === "theory" && (
          <div className="mt-4 space-y-4">
            {!!material?.theory?.summary && <p className="rounded bg-slate-50 p-3 text-slate-700"><b>Tóm tắt:</b> {material.theory.summary}</p>}
            {asArray(material?.theory?.key_concepts).length > 0 && (
              <div>
                <h3 className="mb-2 font-semibold">Key concepts</h3>
                <ul className="list-disc pl-6 text-slate-700">
                  {asArray(material.theory.key_concepts).map((k, i) => <li key={i}>{k}</li>)}
                </ul>
              </div>
            )}
            <MarkdownSafe text={material?.theory?.content_md || topic?.study_guide_md} />
          </div>
        )}

        {!loading && !error && tab === "exercises" && (
          <div className="mt-4 space-y-4">
            {[{ key: "easy", label: "Dễ" }, { key: "medium", label: "Trung bình" }, { key: "hard", label: "Khó" }].map((lv) => (
              <details key={lv.key} className="rounded-xl border border-slate-200 p-3" open>
                <summary className="cursor-pointer font-semibold">{lv.label} ({asArray(exercises?.[lv.key]).length})</summary>
                <div className="mt-3 space-y-3">
                  {asArray(exercises?.[lv.key]).length === 0 && <p className="text-sm text-slate-500">Chưa có bài tập.</p>}
                  {asArray(exercises?.[lv.key]).map((item, idx) => <ExerciseCard key={`${lv.key}-${idx}`} item={item} chunksById={chunksById} />)}
                </div>
              </details>
            ))}
          </div>
        )}

        {!loading && !error && tab === "quiz" && (
          <div className="mt-4 space-y-4">
            <p className="text-sm font-medium text-slate-700">Thời gian còn lại: {Math.floor(timeLeft / 60)}:{String(timeLeft % 60).padStart(2, "0")}</p>
            {miniQuiz.map((q, qIndex) => (
              <div key={qIndex} className="rounded-xl border border-slate-200 p-4">
                <p className="font-semibold">Câu {qIndex + 1}. {q?.question}</p>
                <div className="mt-2 space-y-2">
                  {asArray(q?.options).map((opt, idx) => (
                    <label key={idx} className="flex items-center gap-2 text-sm">
                      <input type="radio" name={`q-${qIndex}`} checked={Number(quizAnswers[qIndex]) === idx} onChange={() => setQuizAnswers((prev) => ({ ...prev, [qIndex]: idx }))} />
                      <span>{opt}</span>
                    </label>
                  ))}
                </div>
              </div>
            ))}
            {!quizResult && <button type="button" className="rounded-lg bg-emerald-600 px-4 py-2 text-white" onClick={onGradeQuiz}>Nộp quiz</button>}
            {quizResult && <p className="rounded-lg bg-emerald-50 p-3 font-semibold text-emerald-700">Kết quả: {quizResult.correct}/{quizResult.total} ({quizResult.score}%)</p>}
          </div>
        )}
      </section>
    </div>
  );
}
