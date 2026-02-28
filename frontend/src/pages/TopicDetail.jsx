import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { apiJson } from "../lib/api";

const QUIZ_DURATION_SEC = 15 * 60;

function MarkdownSafe({ text }) {
  if (!String(text || "").trim()) {
    return <p className="text-slate-500">Chưa có study guide.</p>;
  }

  const lines = String(text).split(/\r?\n/);
  return (
    <div className="space-y-2 text-slate-700">
      {lines.map((line, index) => {
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

function normalizeArray(input) {
  return Array.isArray(input) ? input : [];
}

function getQuestionId(question, index) {
  return question?.question_id ?? question?.id ?? `q-${index}`;
}

export default function TopicDetail() {
  const { topicId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState("study");
  const [topic, setTopic] = useState(null);
  const [loadingTopic, setLoadingTopic] = useState(false);
  const [topicError, setTopicError] = useState("");

  const [openDefinition, setOpenDefinition] = useState({});

  const [quizData, setQuizData] = useState(null);
  const [quizAnswers, setQuizAnswers] = useState({});
  const [quizResult, setQuizResult] = useState(null);
  const [timeLeftSec, setTimeLeftSec] = useState(QUIZ_DURATION_SEC);
  const [loadingQuiz, setLoadingQuiz] = useState(false);
  const [submittingQuiz, setSubmittingQuiz] = useState(false);
  const [quizError, setQuizError] = useState("");

  const docId = searchParams.get("documentId") || searchParams.get("document_id");

  const loadTopic = useCallback(async () => {
    if (!topicId) return;
    setLoadingTopic(true);
    setTopicError("");

    try {
      let data = null;
      try {
        data = await apiJson(`/documents/topics/${topicId}`);
      } catch {
        if (docId) {
          data = await apiJson(`/documents/${docId}/topics/${topicId}`);
        } else {
          throw new Error("Không tải được chi tiết topic");
        }
      }
      setTopic(data || null);
    } catch (error) {
      setTopicError(error?.message || "Không tải được topic");
    } finally {
      setLoadingTopic(false);
    }
  }, [docId, topicId]);

  useEffect(() => {
    loadTopic();
  }, [loadTopic]);

  const generateQuiz = useCallback(async () => {
    if (!topic?.title || loadingQuiz) return;

    setLoadingQuiz(true);
    setQuizError("");
    setQuizResult(null);
    setQuizAnswers({});
    setTimeLeftSec(QUIZ_DURATION_SEC);

    try {
      const payload = {
        topic: topic.title,
        level: "mixed",
        question_count: 10,
        kind: "practice",
      };

      const generated = await apiJson("/quiz/generate", {
        method: "POST",
        body: payload,
      });

      setQuizData(generated || null);
    } catch (error) {
      setQuizError(error?.message || "Không tạo được mini quiz");
    } finally {
      setLoadingQuiz(false);
    }
  }, [loadingQuiz, topic?.title]);

  useEffect(() => {
    if (activeTab !== "quiz" || quizResult || !quizData?.questions?.length) return undefined;

    const timer = setInterval(() => {
      setTimeLeftSec((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [activeTab, quizData?.questions?.length, quizResult]);

  const submitQuiz = useCallback(async () => {
    if (!quizData?.quiz_id) return;

    setSubmittingQuiz(true);
    setQuizError("");

    try {
      const answers = normalizeArray(quizData?.questions).map((question, index) => ({
        question_id: getQuestionId(question, index),
        answer: Number.isInteger(quizAnswers[getQuestionId(question, index)]) ? quizAnswers[getQuestionId(question, index)] : -1,
      }));

      const duration_sec = QUIZ_DURATION_SEC - timeLeftSec;
      const result = await apiJson(`/quiz/${quizData.quiz_id}/submit`, {
        method: "POST",
        body: {
          answers,
          duration_sec,
        },
      });

      setQuizResult(result);
    } catch (error) {
      setQuizError(error?.message || "Nộp quiz thất bại");
    } finally {
      setSubmittingQuiz(false);
    }
  }, [quizAnswers, quizData, timeLeftSec]);

  useEffect(() => {
    if (timeLeftSec !== 0) return;
    if (!quizData?.quiz_id || quizResult || submittingQuiz) return;
    submitQuiz();
  }, [quizData?.quiz_id, quizResult, submitQuiz, submittingQuiz, timeLeftSec]);

  const progressPercent = useMemo(() => {
    const done = Number(topic?.progress_percent ?? topic?.progress ?? 0);
    if (Number.isNaN(done)) return 0;
    return Math.min(100, Math.max(0, Math.round(done)));
  }, [topic?.progress, topic?.progress_percent]);

  const quizQuestions = normalizeArray(quizData?.questions);
  const breakdownMap = useMemo(() => {
    const map = {};
    normalizeArray(quizResult?.breakdown).forEach((row) => {
      map[row?.question_id] = row;
    });
    return map;
  }, [quizResult?.breakdown]);

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900">{topic?.title || "Topic detail"}</h1>
        <div className="mt-3 flex flex-wrap gap-2">
          {normalizeArray(topic?.keywords).map((kw) => (
            <span key={kw} className="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
              #{kw}
            </span>
          ))}
        </div>
        <div className="mt-4">
          <div className="mb-1 flex items-center justify-between text-sm text-slate-600">
            <span>Tiến độ học sinh</span>
            <span>{progressPercent}%</span>
          </div>
          <div className="h-2 rounded-full bg-slate-100">
            <div className="h-2 rounded-full bg-blue-600" style={{ width: `${progressPercent}%` }} />
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex gap-2 border-b border-slate-200 pb-3">
          {[{ key: "study", label: "Học" }, { key: "practice", label: "Bài tập" }, { key: "quiz", label: "Kiểm tra nhanh" }].map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              className={`rounded-lg px-4 py-2 text-sm font-medium ${activeTab === tab.key ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"}`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {loadingTopic && <p className="mt-4 text-slate-500">Đang tải topic...</p>}
        {topicError && <p className="mt-4 text-red-600">{topicError}</p>}

        {!loadingTopic && !topicError && activeTab === "study" && (
          <div className="mt-5 space-y-6">
            <div className="prose max-w-none">
              <MarkdownSafe text={topic?.study_guide_md} />
            </div>

            <div>
              <h3 className="mb-2 text-lg font-semibold">Ý chính</h3>
              <div className="space-y-2">
                {normalizeArray(topic?.key_points).map((point, idx) => (
                  <label key={`${point}-${idx}`} className="flex items-start gap-2 rounded-lg border border-slate-200 p-3">
                    <input type="checkbox" className="mt-1" />
                    <span className="text-slate-700">{point}</span>
                  </label>
                ))}
              </div>
            </div>

            <div>
              <h3 className="mb-2 text-lg font-semibold">Khái niệm</h3>
              <div className="grid gap-3 md:grid-cols-2">
                {normalizeArray(topic?.definitions).map((item, idx) => {
                  const title = item?.term || item?.name || `Khái niệm ${idx + 1}`;
                  const description = item?.definition || item?.description || String(item || "");
                  const isOpen = !!openDefinition[idx];
                  return (
                    <button
                      type="button"
                      key={`${title}-${idx}`}
                      onClick={() => setOpenDefinition((prev) => ({ ...prev, [idx]: !prev[idx] }))}
                      className="rounded-xl border border-slate-200 p-4 text-left"
                    >
                      <p className="font-semibold text-slate-900">{title}</p>
                      <p className="mt-2 text-sm text-slate-600">{isOpen ? description : "Nhấn để lật thẻ"}</p>
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <h3 className="mb-2 text-lg font-semibold">Ví dụ</h3>
              <ul className="list-disc space-y-2 pl-6 text-slate-700">
                {normalizeArray(topic?.examples).map((example, idx) => (
                  <li key={`${idx}-${String(example).slice(0, 20)}`}>{example?.text || example}</li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {!loadingTopic && !topicError && activeTab === "practice" && (
          <div className="mt-5 space-y-4">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-slate-700">
              {topic?.practice_preview || "Chưa có phần bài tập xem trước."}
            </div>

            <div className="flex flex-wrap gap-2">
              {["Dễ", "Trung bình", "Khó"].map((label) => (
                <button key={label} type="button" className="rounded-full border border-slate-300 px-4 py-2 text-sm hover:bg-slate-100">
                  {label}
                </button>
              ))}
            </div>

            <button
              type="button"
              onClick={() => navigate(`/quiz?kind=practice&topicId=${topicId}`)}
              className="rounded-lg bg-blue-600 px-4 py-2 font-medium text-white"
            >
              Làm bài tập
            </button>
          </div>
        )}

        {!loadingTopic && !topicError && activeTab === "quiz" && (
          <div className="mt-5 space-y-4">
            {!quizData && (
              <button type="button" onClick={generateQuiz} disabled={loadingQuiz} className="rounded-lg bg-blue-600 px-4 py-2 text-white disabled:opacity-60">
                {loadingQuiz ? "Đang tạo mini quiz..." : "Bắt đầu mini quiz 10 câu"}
              </button>
            )}

            {quizData && !quizResult && (
              <>
                <div className="rounded-xl bg-amber-50 p-3 text-sm font-medium text-amber-700">
                  ⏱️ Thời gian còn lại: {Math.floor(timeLeftSec / 60)}:{String(timeLeftSec % 60).padStart(2, "0")}
                </div>

                <div className="space-y-4">
                  {quizQuestions.map((question, qIdx) => {
                    const questionId = getQuestionId(question, qIdx);
                    const options = normalizeArray(question?.options);
                    return (
                      <div key={questionId} className="rounded-xl border border-slate-200 p-4">
                        <p className="font-semibold">Câu {qIdx + 1}. {question?.stem || question?.question}</p>
                        <div className="mt-3 space-y-2">
                          {options.map((option, optIdx) => (
                            <label key={`${questionId}-${optIdx}`} className="flex items-center gap-2">
                              <input
                                type="radio"
                                name={String(questionId)}
                                checked={quizAnswers[questionId] === optIdx}
                                onChange={() => setQuizAnswers((prev) => ({ ...prev, [questionId]: optIdx }))}
                              />
                              <span>{option}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>

                <button type="button" onClick={submitQuiz} disabled={submittingQuiz} className="rounded-lg bg-emerald-600 px-4 py-2 text-white disabled:opacity-60">
                  {submittingQuiz ? "Đang nộp..." : "Nộp mini quiz"}
                </button>
              </>
            )}

            {quizResult && (
              <div className="space-y-3">
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                  <p className="text-lg font-bold text-emerald-700">Điểm số: {quizResult?.score_percent ?? 0}%</p>
                  <p className="text-sm text-emerald-700">Đúng {quizResult?.correct_count ?? 0}/{quizResult?.total ?? quizQuestions.length} câu</p>
                </div>

                {quizQuestions.map((question, qIdx) => {
                  const questionId = getQuestionId(question, qIdx);
                  const breakdown = breakdownMap[questionId];
                  const options = normalizeArray(question?.options);
                  const chosen = breakdown?.chosen;
                  const correct = breakdown?.correct;
                  const isCorrect = !!breakdown?.is_correct;

                  return (
                    <div key={`${questionId}-result`} className={`rounded-xl border p-4 ${isCorrect ? "border-emerald-200 bg-emerald-50" : "border-red-200 bg-red-50"}`}>
                      <p className="font-semibold">
                        Câu {qIdx + 1}. {question?.stem || question?.question} - {isCorrect ? "Đúng" : "Sai"}
                      </p>
                      <p className="text-sm">
                        Đáp án của bạn: {Number.isInteger(chosen) ? options[chosen] : "(chưa chọn)"}
                      </p>
                      <p className="text-sm font-medium">Đáp án đúng: {Number.isInteger(correct) ? options[correct] : "N/A"}</p>
                    </div>
                  );
                })}

                <button type="button" onClick={() => navigate("/learning-path")} className="rounded-lg bg-blue-600 px-4 py-2 text-white">
                  Tiếp tục học
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
