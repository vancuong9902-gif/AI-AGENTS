import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";

function MarkdownSafe({ text }) {
  if (!String(text || "").trim()) {
    return <p className="text-slate-500">Chưa có nội dung học cho topic này.</p>;
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

function getQuestionId(question, index) {
  return question?.question_id ?? question?.id ?? index + 1;
}

const LEVEL_MAP = {
  easy: "beginner",
  medium: "intermediate",
  hard: "advanced",
};

export default function TopicDetail() {
  const { documentId, topicId } = useParams();
  const navigate = useNavigate();
  const { userId } = useAuth();

  const [tab, setTab] = useState("study");
  const [topic, setTopic] = useState(null);
  const [loadingTopic, setLoadingTopic] = useState(false);
  const [topicError, setTopicError] = useState("");

  const [quiz, setQuiz] = useState(null);
  const [answers, setAnswers] = useState({});
  const [quizResult, setQuizResult] = useState(null);
  const [loadingQuiz, setLoadingQuiz] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [quizError, setQuizError] = useState("");

  const fetchTopic = useCallback(async () => {
    if (!documentId || !topicId) return;
    setLoadingTopic(true);
    setTopicError("");
    try {
      const data = await apiJson(`/documents/${documentId}/topics/${topicId}?include_content=1`);
      setTopic(data || null);
    } catch (error) {
      setTopicError(error?.message || "Không tải được topic");
    } finally {
      setLoadingTopic(false);
    }
  }, [documentId, topicId]);

  useEffect(() => {
    fetchTopic();
  }, [fetchTopic]);

  const onGenerateQuickQuiz = useCallback(async () => {
    if (!topic?.title || loadingQuiz) return;
    setLoadingQuiz(true);
    setQuizError("");
    setQuizResult(null);
    setAnswers({});
    try {
      const generated = await apiJson("/quiz/generate", {
        method: "POST",
        body: {
          user_id: Number(userId || 1),
          topic: topic.title,
          level: "intermediate",
          question_count: 5,
          rag: {
            query: `${topic.title} practice questions`,
            top_k: 6,
            filters: { document_id: Number(documentId), topic_id: Number(topicId) },
          },
        },
      });
      setQuiz(generated);
    } catch (error) {
      setQuizError(error?.message || "Không thể tạo quiz nhanh");
    } finally {
      setLoadingQuiz(false);
    }
  }, [documentId, loadingQuiz, topic?.title, topicId, userId]);

  const onSubmitQuickQuiz = useCallback(async () => {
    if (!quiz?.quiz_id) return;
    setSubmitLoading(true);
    setQuizError("");
    try {
      const payloadAnswers = asArray(quiz?.questions).map((q, index) => {
        const qid = getQuestionId(q, index);
        return {
          question_id: Number(qid),
          answer: Number.isInteger(answers[qid]) ? answers[qid] : -1,
        };
      });

      const result = await apiJson(`/quiz/${quiz.quiz_id}/submit`, {
        method: "POST",
        body: {
          user_id: Number(userId || 1),
          duration_sec: 0,
          answers: payloadAnswers,
        },
      });
      setQuizResult(result);
    } catch (error) {
      setQuizError(error?.message || "Nộp quiz thất bại");
    } finally {
      setSubmitLoading(false);
    }
  }, [answers, quiz, userId]);

  const breakdownMap = useMemo(() => {
    const out = {};
    asArray(quizResult?.breakdown).forEach((row) => {
      out[row?.question_id] = row;
    });
    return out;
  }, [quizResult?.breakdown]);

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900">{topic?.display_title || topic?.title || "Topic detail"}</h1>
        <p className="mt-2 text-sm text-slate-500">Document #{documentId} • Topic #{topicId}</p>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex gap-2 border-b border-slate-200 pb-3">
          {[{ key: "study", label: "Nội dung học" }, { key: "book-practice", label: "Bài tập trong sách" }, { key: "quick-quiz", label: "Kiểm tra nhanh" }].map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setTab(item.key)}
              className={`rounded-lg px-4 py-2 text-sm font-medium ${tab === item.key ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"}`}
            >
              {item.label}
            </button>
          ))}
        </div>

        {loadingTopic && <p className="mt-4 text-slate-500">Đang tải topic...</p>}
        {topicError && <p className="mt-4 text-red-600">{topicError}</p>}

        {!loadingTopic && !topicError && tab === "study" && (
          <div className="mt-5 space-y-4">
            <MarkdownSafe text={topic?.study_guide_md} />
            <button
              type="button"
              onClick={() => navigate(`/practice?documentId=${documentId}&topic=${topicId}&level=medium`)}
              className="rounded-lg bg-blue-600 px-4 py-2 font-medium text-white"
            >
              Sang luyện tập theo topic
            </button>
          </div>
        )}

        {!loadingTopic && !topicError && tab === "book-practice" && (
          <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4 text-slate-700 whitespace-pre-wrap">
            {topic?.practice || topic?.practice_preview || "Chưa tìm thấy phần bài tập trong sách."}
          </div>
        )}

        {!loadingTopic && !topicError && tab === "quick-quiz" && (
          <div className="mt-5 space-y-4">
            {!quiz && (
              <button type="button" onClick={onGenerateQuickQuiz} disabled={loadingQuiz} className="rounded-lg bg-blue-600 px-4 py-2 text-white disabled:opacity-60">
                {loadingQuiz ? "Đang tạo quiz..." : "Tạo quiz nhanh 5 câu"}
              </button>
            )}

            {quiz && !quizResult && (
              <>
                {asArray(quiz.questions).map((question, qIndex) => {
                  const qid = getQuestionId(question, qIndex);
                  return (
                    <div key={qid} className="rounded-xl border border-slate-200 p-4">
                      <p className="font-semibold">Câu {qIndex + 1}. {question?.stem}</p>
                      <div className="mt-3 space-y-2">
                        {asArray(question?.options).map((option, optIndex) => (
                          <label key={`${qid}-${optIndex}`} className="flex items-center gap-2">
                            <input
                              type="radio"
                              name={String(qid)}
                              checked={answers[qid] === optIndex}
                              onChange={() => setAnswers((prev) => ({ ...prev, [qid]: optIndex }))}
                            />
                            <span>{option}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  );
                })}

                <button type="button" onClick={onSubmitQuickQuiz} disabled={submitLoading} className="rounded-lg bg-emerald-600 px-4 py-2 text-white disabled:opacity-60">
                  {submitLoading ? "Đang chấm..." : "Nộp và chấm ngay"}
                </button>
              </>
            )}

            {quizResult && (
              <div className="space-y-3">
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                  <p className="text-lg font-bold text-emerald-700">Điểm: {quizResult?.score_percent ?? 0}%</p>
                  <p className="text-sm text-emerald-700">Đúng {quizResult?.correct_count ?? 0}/{quizResult?.total ?? 0} câu</p>
                </div>

                {asArray(quiz?.questions).map((question, qIndex) => {
                  const qid = getQuestionId(question, qIndex);
                  const row = breakdownMap[qid];
                  if (!row) return null;
                  const options = asArray(question?.options);
                  return (
                    <div key={`${qid}-r`} className={`rounded-xl border p-4 ${row?.is_correct ? "border-emerald-200 bg-emerald-50" : "border-red-200 bg-red-50"}`}>
                      <p className="font-semibold">Câu {qIndex + 1}: {row?.is_correct ? "Đúng" : "Sai"}</p>
                      <p className="text-sm">Bạn chọn: {Number.isInteger(row?.chosen) ? options[row.chosen] : "(chưa chọn)"}</p>
                      <p className="text-sm">Đáp án đúng: {Number.isInteger(row?.correct) ? options[row.correct] : "N/A"}</p>
                      {!row?.is_correct && row?.explanation && <p className="mt-2 text-sm text-slate-700">Giải thích: {row.explanation}</p>}
                    </div>
                  );
                })}

                <button
                  type="button"
                  onClick={() => navigate(`/practice?documentId=${documentId}&topic=${topicId}&level=${Object.keys(LEVEL_MAP)[1]}`)}
                  className="rounded-lg bg-blue-600 px-4 py-2 text-white"
                >
                  Luyện thêm 10-20 câu
                </button>
              </div>
            )}

            {quizError && <p className="text-red-600">{quizError}</p>}
          </div>
        )}
      </section>
    </div>
  );
}
