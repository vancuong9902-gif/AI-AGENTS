import { useCallback, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";

const LEVEL_TO_BACKEND = {
  easy: "beginner",
  medium: "intermediate",
  hard: "advanced",
};

const LEVEL_LABEL = {
  easy: "Dễ",
  medium: "Trung bình",
  hard: "Khó",
};

function asArray(v) {
  return Array.isArray(v) ? v : [];
}

function getQuestionId(question, index) {
  return question?.question_id ?? question?.id ?? index + 1;
}

export default function StudentPractice() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { userId } = useAuth();

  const documentId = searchParams.get("documentId") || "";
  const topicParam = searchParams.get("topic") || "";
  const [level, setLevel] = useState((searchParams.get("level") || "medium").toLowerCase());
  const [questionCount, setQuestionCount] = useState(10);

  const [quiz, setQuiz] = useState(null);
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const normalizedLevel = LEVEL_TO_BACKEND[level] ? level : "medium";

  const onGenerate = useCallback(async () => {
    setLoading(true);
    setError("");
    setResult(null);
    setAnswers({});
    try {
      const payload = {
        user_id: Number(userId || 1),
        topic: topicParam || `Topic ${documentId}`,
        level: LEVEL_TO_BACKEND[normalizedLevel],
        question_count: Number(questionCount),
        rag: {
          query: `${topicParam || "topic"} ${LEVEL_LABEL[normalizedLevel]} practice`,
          top_k: 8,
          filters: { document_id: Number(documentId) || undefined, topic_id: Number(topicParam) || undefined },
        },
      };

      const generated = await apiJson("/quiz/generate", {
        method: "POST",
        body: payload,
      });
      setQuiz(generated);
    } catch (e) {
      setError(e?.message || "Không tạo được bộ luyện tập");
    } finally {
      setLoading(false);
    }
  }, [documentId, normalizedLevel, questionCount, topicParam, userId]);

  const onSubmit = useCallback(async () => {
    if (!quiz?.quiz_id) return;
    setSubmitting(true);
    setError("");
    try {
      const payloadAnswers = asArray(quiz?.questions).map((q, index) => {
        const qid = getQuestionId(q, index);
        return {
          question_id: Number(qid),
          answer: Number.isInteger(answers[qid]) ? answers[qid] : -1,
        };
      });

      const submitted = await apiJson(`/quiz/${quiz.quiz_id}/submit`, {
        method: "POST",
        body: {
          user_id: Number(userId || 1),
          duration_sec: 0,
          answers: payloadAnswers,
        },
      });
      setResult(submitted);
    } catch (e) {
      setError(e?.message || "Nộp bài thất bại");
    } finally {
      setSubmitting(false);
    }
  }, [answers, quiz, userId]);

  const breakdownMap = useMemo(() => {
    const out = {};
    asArray(result?.breakdown).forEach((item) => {
      out[item?.question_id] = item;
    });
    return out;
  }, [result?.breakdown]);

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
        <h1 className="text-2xl font-bold text-slate-900">Luyện tập theo topic</h1>
        <p className="text-sm text-slate-500">documentId={documentId || "?"} • topic={topicParam || "?"}</p>

        <div className="flex flex-wrap items-center gap-3">
          {Object.keys(LEVEL_TO_BACKEND).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setLevel(key)}
              className={`rounded-full px-4 py-2 text-sm ${normalizedLevel === key ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"}`}
            >
              {LEVEL_LABEL[key]}
            </button>
          ))}

          <select value={questionCount} onChange={(e) => setQuestionCount(Number(e.target.value))} className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
            <option value={10}>10 câu</option>
            <option value={15}>15 câu</option>
            <option value={20}>20 câu</option>
          </select>

          <button type="button" onClick={onGenerate} disabled={loading} className="rounded-lg bg-blue-600 px-4 py-2 text-white disabled:opacity-60">
            {loading ? "Đang tạo..." : "Tạo bộ luyện tập"}
          </button>
        </div>
      </section>

      {!!error && <p className="text-red-600">{error}</p>}

      {quiz && !result && (
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
          {asArray(quiz?.questions).map((question, index) => {
            const qid = getQuestionId(question, index);
            return (
              <div key={qid} className="rounded-xl border border-slate-200 p-4">
                <p className="font-semibold">Câu {index + 1}. {question?.stem}</p>
                <div className="mt-2 space-y-2">
                  {asArray(question?.options).map((opt, optIdx) => (
                    <label key={`${qid}-${optIdx}`} className="flex items-center gap-2">
                      <input
                        type="radio"
                        name={String(qid)}
                        checked={answers[qid] === optIdx}
                        onChange={() => setAnswers((prev) => ({ ...prev, [qid]: optIdx }))}
                      />
                      <span>{opt}</span>
                    </label>
                  ))}
                </div>
              </div>
            );
          })}

          <button type="button" onClick={onSubmit} disabled={submitting} className="rounded-lg bg-emerald-600 px-4 py-2 text-white disabled:opacity-60">
            {submitting ? "Đang chấm..." : "Nộp bài"}
          </button>
        </section>
      )}

      {result && (
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
            <p className="text-lg font-bold text-emerald-700">Điểm: {result?.score_percent ?? 0}%</p>
            <p className="text-sm text-emerald-700">Đúng {result?.correct_count ?? 0}/{result?.total ?? 0} câu</p>
          </div>

          {asArray(quiz?.questions).map((q, index) => {
            const qid = getQuestionId(q, index);
            const row = breakdownMap[qid];
            if (!row || row?.is_correct) return null;
            const options = asArray(q?.options);
            return (
              <div key={`${qid}-wrong`} className="rounded-xl border border-red-200 bg-red-50 p-4">
                <p className="font-semibold">Câu {index + 1} sai</p>
                <p className="text-sm">Bạn chọn: {Number.isInteger(row?.chosen) ? options[row.chosen] : "(chưa chọn)"}</p>
                <p className="text-sm">Đáp án đúng: {Number.isInteger(row?.correct) ? options[row.correct] : "N/A"}</p>
                {!!row?.explanation && <p className="text-sm mt-1">Giải thích: {row.explanation}</p>}
              </div>
            );
          })}

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => navigate(`/tutor?topic=${encodeURIComponent(topicParam)}&level=${encodeURIComponent(normalizedLevel)}`)}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-white"
            >
              Hỏi Tutor về câu sai
            </button>
            <button type="button" onClick={onGenerate} className="rounded-lg bg-slate-700 px-4 py-2 text-white">
              Làm bộ mới
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
