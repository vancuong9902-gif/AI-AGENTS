import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/useAuth";

const kindLabelMap = {
  diagnostic_pre: "Đầu vào",
  midterm: "Bài tổng hợp",
  diagnostic_post: "Cuối kỳ",
};

function fmtTime(sec) {
  if (sec == null) return "--:--";
  const total = Math.max(0, Number(sec) || 0);
  const mm = String(Math.floor(total / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

export default function AssessmentTake() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { userId } = useAuth();
  const assessmentId = Number(id);

  const [data, setData] = useState(null);
  const [attemptId, setAttemptId] = useState(null);
  const [answers, setAnswers] = useState({});
  const [timeLeftSec, setTimeLeftSec] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pathAssigned, setPathAssigned] = useState(false);
  const [citationMap, setCitationMap] = useState({});
  const [explanationsByQuestion, setExplanationsByQuestion] = useState({});
  const [explanationsLoading, setExplanationsLoading] = useState(false);
  const autoSubmittedRef = useRef(false);
  const warningShownRef = useRef({ five: false, one: false });
  const diagnosticBannerRef = useRef(null);

  const learningPathBannerRef = useRef(null);

  const qMap = useMemo(() => {
    const m = {};
    for (const q of data?.questions || []) {
      m[q.question_id] = q;
    }
    return m;
  }, [data]);

  const timeLimitSec = useMemo(() => {
    const direct = Number(data?.duration_seconds || 0);
    if (Number.isFinite(direct) && direct > 0) return Math.round(direct);
    const mins = Number(data?.time_limit_minutes || 0);
    return Number.isFinite(mins) && mins > 0 ? Math.round(mins * 60) : 0;
  }, [data]);

  const fmtTime = (sec) => {
    if (sec == null) return "--:--";
    const s = Math.max(0, Math.floor(sec));
    const mm = String(Math.floor(s / 60)).padStart(2, "0");
    const ss = String(s % 60).padStart(2, "0");
    return `${mm}:${ss}`;
  };

  const levelLabel = (score) => {
    const s = Number(score || 0);
    if (s < 40) return "Yếu";
    if (s < 60) return "Trung bình";
    if (s < 80) return "Khá";
    return "Giỏi";
  };

  const levelTheme = (score) => {
    const s = Number(score || 0);
    if (s < 40) return { label: "Yếu", color: "#cf1322", bg: "#fff1f0", track: "#ffccc7" };
    if (s < 60) return { label: "Trung bình", color: "#d48806", bg: "#fff7e6", track: "#ffd591" };
    if (s < 80) return { label: "Khá", color: "#096dd9", bg: "#e6f4ff", track: "#91caff" };
    return { label: "Giỏi", color: "#722ed1", bg: "#f9f0ff", track: "#d3adf7" };
  };

  const levelBadgeTheme = (levelValue) => {
    const level = String(levelValue || "").toLowerCase();
    if (level.includes("yếu") || level.includes("yeu") || level.includes("beginner")) {
      return { color: "#cf1322", bg: "#fff1f0", border: "#ffa39e" };
    }
    if (level.includes("trung bình") || level.includes("trung_binh") || level.includes("intermediate")) {
      return { color: "#d48806", bg: "#fff7e6", border: "#ffd591" };
    }
    if (level.includes("khá") || level.includes("kha") || level.includes("proficient")) {
      return { color: "#096dd9", bg: "#e6f4ff", border: "#91caff" };
    }
    return { color: "#722ed1", bg: "#f9f0ff", border: "#d3adf7" };
  };
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [progress, setProgress] = useState(null);
  const [toasts, setToasts] = useState([]);

  const warnedRef = useRef({ five: false, one: false });
  const autoSubmitRef = useRef(false);

  const examMode = location.state?.examMode || new URLSearchParams(location.search).get("mode");
  const classroomId = Number(localStorage.getItem("active_classroom_id") || 0);

  const questions = data?.questions || [];
  const answeredCount = useMemo(() => Object.keys(answers).length, [answers]);
  const isFinalExam = String(data?.kind || "").toLowerCase() === "diagnostic_post";

  const pushToast = (message) => {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts((prev) => [...prev, { id, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3000);
  };

  const loadProgress = async () => {
    if (!classroomId || !userId) return;
    try {
      const row = await apiJson(`/lms/student/${Number(userId)}/progress?classroom_id=${classroomId}`);
      setProgress(row || null);
    } catch {
      // optional panel only
    }
  };

  const weakestTopic = useMemo(() => {
    const topicMap = {};
    for (const item of result?.answer_review || []) {
      if (item?.is_correct) continue;
      const key = String(item?.topic || "").trim();
      if (!key) continue;
      topicMap[key] = (topicMap[key] || 0) + 1;
    }
    let best = "";
    let maxWrong = 0;
    for (const [topic, cnt] of Object.entries(topicMap)) {
      if (cnt > maxWrong) {
        maxWrong = cnt;
        best = topic;
      }
    }
    return best;
  }, [result]);

  const topicBreakdown = useMemo(() => {
    const topicMap = {};
    for (const item of result?.answer_review || []) {
      const topic = String(item?.topic || "Chưa phân loại").trim() || "Chưa phân loại";
      if (!topicMap[topic]) {
        topicMap[topic] = { topic, correct: 0, wrong: 0, score: 0, max: 0 };
      }
      if (item?.is_correct) topicMap[topic].correct += 1;
      else topicMap[topic].wrong += 1;
      topicMap[topic].score += Number(item?.score_points || 0);
      topicMap[topic].max += Number(item?.max_points || 1);
    }

    return Object.values(topicMap)
      .map((entry) => {
        const percent = Math.round((entry.score / Math.max(1, entry.max)) * 100);
        let remark = "Cần cải thiện";
        if (percent >= 80) remark = "Nắm rất chắc";
        else if (percent >= 60) remark = "Ổn, cần luyện thêm";
        return { ...entry, percent, remark };
      })
      .sort((a, b) => a.percent - b.percent);
  }, [result]);

  const normalizedRecommendations = useMemo(() => {
    if (Array.isArray(aiRecommendations)) return aiRecommendations;
    if (Array.isArray(aiRecommendations?.recommendations)) return aiRecommendations.recommendations;
    if (Array.isArray(aiRecommendations?.topics)) return aiRecommendations.topics;
    return [];
  }, [aiRecommendations]);

  const recommendedTopics = useMemo(
    () => normalizedRecommendations.map((it) => String(it?.topic || it?.name || it || "").trim()).filter(Boolean),
    [normalizedRecommendations],
  );

  const resolvedScore = Number(result?.total_score_percent ?? result?.score_percent ?? 0);
  const scoreTheme = levelTheme(resolvedScore);


  useEffect(() => {
    const allSources = [];
    (result?.answer_review || []).forEach((row) => {
      if (Array.isArray(row?.sources)) allSources.push(...row.sources);
    });
    const chunkIds = [...new Set(allSources.map((src) => Number(src?.chunk_id)).filter((id) => Number.isInteger(id) && id > 0))];
    if (chunkIds.length === 0) {
      setCitationMap({});
      return;
    }

    let ignore = false;
    (async () => {
      try {
        const data = await apiJson(`/documents/chunks/citations?chunk_ids=${chunkIds.join(",")}`);
        if (ignore) return;
        const map = {};
        (Array.isArray(data) ? data : []).forEach((item) => {
          if (Number.isInteger(item?.chunk_id)) map[item.chunk_id] = item;
        });
        setCitationMap(map);
      } catch {
        if (!ignore) setCitationMap({});
      }
    })();

    return () => {
      ignore = true;
    };
  }, [result]);

  const pageLabel = (cite) => {
    if (!cite) return "";
    const start = Number(cite?.page_start);
    const end = Number(cite?.page_end);
    if (Number.isInteger(start) && Number.isInteger(end)) return start === end ? `Trang ${start}` : `Trang ${start}–${end}`;
    if (Number.isInteger(start)) return `Trang ${start}`;
    return "";
  };
  useEffect(() => {
    const loadExplanations = async () => {
      if (!result?.attempt_id) return;
      const rows = result?.answer_review || result?.breakdown || [];
      const missingWrongExplanation = rows.some((b) => !b?.is_correct && !String(b?.explanation || "").trim());
      if (!missingWrongExplanation) return;

      setExplanationsLoading(true);
      try {
        const explanationMap = await apiJson(`/assessments/${assessmentId}/explanations?attempt_id=${Number(result.attempt_id)}`);
        setExplanationsByQuestion(explanationMap || {});
      } catch {
        setExplanationsByQuestion({});
      } finally {
        setExplanationsLoading(false);
      }
    };

    loadExplanations();
  }, [assessmentId, result]);

  const load = async () => {
    if (!Number.isFinite(assessmentId)) return;
    setLoading(true);
    setError("");
    setResult(null);
    warnedRef.current = { five: false, one: false };
    autoSubmitRef.current = false;

    try {
      const assessment = await apiJson(`/assessments/${assessmentId}`);
      setData(assessment || null);
      const started = await apiJson("/attempts/start", {
        method: "POST",
        body: { quiz_id: Number(assessment?.assessment_id || assessmentId), student_id: Number(userId || 0) },
      });
      setAttemptId(Number(started?.attempt_id || 0) || null);
      const initialSec = Number(started?.remaining_seconds || assessment?.duration_seconds || 0);
      setTimeLeftSec(Number.isFinite(initialSec) && initialSec > 0 ? initialSec : null);
      if (String(assessment?.kind || "").toLowerCase() === "diagnostic_post") {
        loadProgress();
      }
    } catch (e) {
      setError(e?.message || "Không tải được bài kiểm tra.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assessmentId]);

  useEffect(() => {
    if (timeLeftSec == null || result || submitting) return;
    const t = setInterval(() => {
      setTimeLeftSec((prev) => (prev == null ? prev : Math.max(0, prev - 1)));
    }, 1000);
    return () => clearInterval(t);
  }, [timeLeftSec, result, submitting]);

  useEffect(() => {
    if (timeLeftSec == null || result || submitting) return;
    if (timeLeftSec <= 300 && !warnedRef.current.five) {
      warnedRef.current.five = true;
      pushToast("Còn 5 phút");
    }
    if (timeLeftSec <= 60 && !warnedRef.current.one) {
      warnedRef.current.one = true;
      pushToast("Còn 1 phút");
    }
    if (timeLeftSec <= 0 && !autoSubmitRef.current) {
      autoSubmitRef.current = true;
      submit(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeLeftSec, result, submitting]);

  const submit = async (auto = false) => {
    if (!attemptId || !data) return;
    setSubmitting(true);
    setError("");
    try {
      const answerList = questions.map((q) => ({
        question_id: q.question_id,
        answer_index: answers[q.question_id]?.answer_index ?? null,
        answer_text: answers[q.question_id]?.answer_text ?? null,
      }));
      const r = await apiJson(`/attempts/${attemptId}/submit`, {
        method: "POST",
        body: { answers: answerList, force: Boolean(auto) },
      });
      setResult(r);
      if (String(data?.kind || "").toLowerCase() === "diagnostic_post") {
        loadProgress();
      }
    } catch (e) {
      setError(e?.message || "Nộp bài thất bại.");
      setSubmitting(false);
      return;
    }
    setSubmitting(false);
  };

  const renderSources = (srcs) => {
    if (!Array.isArray(srcs) || srcs.length === 0) return null;
    return (
      <div style={{ marginTop: 8, fontSize: 13, color: "#555" }}>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>Nguồn tham khảo</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {srcs.slice(0, 8).map((s, i) => (
            <span
              key={i}
              style={{
                border: "1px solid #eee",
                background: "#fafafa",
                borderRadius: 999,
                padding: "4px 10px",
              }}
            >
              chunk #{s?.chunk_id ?? "?"}{citationMap?.[s?.chunk_id] ? ` · ${pageLabel(citationMap[s.chunk_id])}` : ""}
            </span>
          ))}
        </div>
      </div>
    );
  };

  const sectionMeta = {
    easy: {
      id: "section-easy",
      className: "easy",
      title: "PHẦN I: CÂU HỎI CƠ BẢN",
      label: "🟢 CƠ BẢN",
      color: "#52c41a",
      bg: "#f6ffed",
      questions: groupedQuestions.easy,
    },
    medium: {
      id: "section-medium",
      className: "medium",
      title: "PHẦN II: CÂU HỎI VẬN DỤNG",
      label: "🟡 VẬN DỤNG",
      color: "#fa8c16",
      bg: "#fff7e6",
      questions: groupedQuestions.medium,
    },
    hard: {
      id: "section-hard",
      className: "hard",
      title: "PHẦN III: CÂU HỎI NÂNG CAO",
      label: "🔴 NÂNG CAO",
      color: "#f5222d",
      bg: "#fff1f0",
      questions: groupedQuestions.hard,
    },
  };

  const renderQuestionCard = (q, orderNo) => (
    <div
      key={q.question_id}
      style={{ background: "#fff", borderRadius: 12, padding: 12, boxShadow: "0 2px 10px rgba(0,0,0,0.06)" }}
    >
      <div style={{ fontWeight: 700, marginBottom: 6 }}>
        Câu {orderNo} ({q.type === "mcq" ? "Trắc nghiệm" : "Tự luận"}) • {detectDifficulty(q)}
        {Number(q?.estimated_minutes || 0) > 0 ? (
          <span style={{ fontWeight: 500, color: "#666" }}> • ~{q.estimated_minutes} phút</span>
        ) : null}
      </div>
      <div style={{ whiteSpace: "pre-wrap" }}>{q.stem}</div>

      {q.type === "mcq" && (
        <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
          {(q.options || []).map((op, i) => (
            <label key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
              <input
                type="radio"
                name={`q_${q.question_id}`}
                checked={(answers[q.question_id]?.answer_index ?? null) === i}
                onChange={() => setMcq(q.question_id, i)}
                disabled={!!result || attemptLocked}
              />
              <span>{op}</span>
            </label>
          ))}
        </div>
      )}

      {q.type === "essay" && (
        <div style={{ marginTop: 10 }}>
          <textarea
            rows={5}
            value={answers[q.question_id]?.answer_text ?? ""}
            onChange={(e) => setEssay(q.question_id, e.target.value)}
            placeholder="Nhập câu trả lời tự luận..."
            style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #ddd" }}
            disabled={!!result || attemptLocked}
          />
          <div style={{ color: "#666", marginTop: 6 }}>Thang điểm: {q.max_points || 10} (AI sẽ chấm theo rubric)</div>
        </div>
      )}
    </div>
  );

  if (loading) {
    return (
      <div style={{ maxWidth: 900, margin: "0 auto", padding: 16 }}>
        <h2>Đang tải…</h2>
      </div>
    );
  }
  if (loading) return <div style={{ padding: 16 }}>Đang tải bài kiểm tra…</div>;
  if (error && !data) return <div style={{ padding: 16, color: "#b42318" }}>{error}</div>;

  if (result) {
    const score = Number(result?.total_score_percent ?? result?.score_percent ?? 0);
    const delta = Number(progress?.delta ?? 0);

    return (
      <div style={{ maxWidth: 980, margin: "0 auto", padding: 16 }}>
        <h2>Kết quả bài kiểm tra</h2>
        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12, padding: 16 }}>
          <div>Điểm: <b>{Math.round(score)}/100</b></div>
          <div>Đúng: {Number(result?.correct_count || 0)} / {Number(result?.total_questions || questions.length)}</div>
          <div>Thời gian làm bài: {fmtTime(Number(result?.time_spent_seconds || 0))}</div>
        </div>

        {isFinalExam && (
          <div style={{ marginTop: 12, background: "#f5f3ff", border: "1px solid #c4b5fd", borderRadius: 12, padding: 16 }}>
            <h3 style={{ marginTop: 0, color: "#5b21b6" }}>So sánh đầu vào vs cuối kỳ</h3>
            <div>Đầu vào: <b>{progress?.pre_score != null ? `${Number(progress.pre_score).toFixed(1)}%` : "Chưa có"}</b></div>
            <div>Cuối kỳ: <b>{progress?.post_score != null ? `${Number(progress.post_score).toFixed(1)}%` : `${score.toFixed(1)}%`}</b></div>
            <div>Mức cải thiện: <b style={{ color: delta >= 0 ? "#166534" : "#b91c1c" }}>{delta >= 0 ? "+" : ""}{Number.isFinite(delta) ? delta.toFixed(1) : "0.0"}%</b></div>
            <p style={{ marginBottom: 0, color: "#4338ca" }}>{delta >= 0 ? "Bạn đã tiến bộ rõ rệt sau quá trình học. Tiếp tục phát huy!" : "Kết quả cuối kỳ chưa cao hơn đầu vào. Hãy xem lại phần sai để cải thiện."}</p>
          </div>
        )}

        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <Link to="/assessments"><button style={{ padding: "8px 12px" }}>⬅ Danh sách</button></Link>
          {examMode === "final" ? <button onClick={() => navigate("/final-exam")} style={{ padding: "8px 12px" }}>Về trang Cuối kỳ</button> : null}
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>{data?.title || "Bài kiểm tra"}</h2>
          <div style={{ color: "#666" }}>
            Nhãn: <b>{kindLabelMap[data?.kind] || data?.kind || "Khác"}</b>
          </div>
          {String(data?.kind || "").toLowerCase() === "diagnostic_pre" && (
            <div style={{ marginTop: 8, display: "inline-block", background: "#eff6ff", color: "#1d4ed8", border: "1px solid #93c5fd", borderRadius: 999, padding: "4px 10px", fontWeight: 700 }}>
              ĐÂY LÀ BÀI KIỂM TRA ĐẦU VÀO
            </div>
          )}
          {isFinalExam && (
            <div style={{ marginTop: 8, display: "inline-block", background: "#f5f3ff", color: "#6d28d9", border: "1px solid #c4b5fd", borderRadius: 999, padding: "4px 10px", fontWeight: 700 }}>
              🎓 ĐÂY LÀ BÀI KIỂM TRA CUỐI KỲ
            </div>
          )}
        </div>
        <div style={{ fontWeight: 800, color: timeLeftSec <= 300 ? "#dc2626" : "#111827" }}>⏱ {fmtTime(timeLeftSec)}</div>
      </div>

      {error ? <div style={{ marginTop: 12, color: "#b42318" }}>{error}</div> : null}

      <div style={{ marginTop: 8, color: "#6b7280" }}>Đã trả lời {answeredCount}/{questions.length} câu</div>

      <div style={{ marginTop: 12, display: "grid", gap: 12 }}>
        {questions.map((q, idx) => (
          <div key={q.question_id} style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12, padding: 12 }}>
            <div style={{ color: "#6b7280", fontSize: 13 }}>Câu {idx + 1}</div>
            <div style={{ fontWeight: 700 }}>{q.stem}</div>

            {Array.isArray(q.options) && q.options.length > 0 ? (
              <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
                {q.options.map((op, i) => (
                  <label key={`${q.question_id}-${i}`} style={{ display: "flex", gap: 8, alignItems: "center", border: "1px solid #e5e7eb", borderRadius: 10, padding: 8 }}>
                    <input
                      type="radio"
                      checked={answers[q.question_id]?.answer_index === i}
                      onChange={() => setAnswers((prev) => ({ ...prev, [q.question_id]: { ...prev[q.question_id], answer_index: i } }))}
                      disabled={submitting}
                    />
                    <span>{op}</span>
                  </label>
                ))}
              </div>
            ) : (
              <textarea
                rows={4}
                value={answers[q.question_id]?.answer_text || ""}
                onChange={(e) => setAnswers((prev) => ({ ...prev, [q.question_id]: { ...prev[q.question_id], answer_text: e.target.value } }))}
                placeholder="Nhập câu trả lời..."
                style={{ marginTop: 10, width: "100%", border: "1px solid #e5e7eb", borderRadius: 10, padding: 8 }}
              />
            )}
          </div>
        ))}
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <Link to="/assessments"><button style={{ padding: "8px 12px" }}>⬅ Danh sách</button></Link>
        <button onClick={() => submit(false)} disabled={submitting} style={{ padding: "8px 12px", background: "#2563eb", color: "#fff", border: "none", borderRadius: 8 }}>
          {submitting ? "Đang nộp..." : "Nộp bài"}
        </button>
      </div>

      <div style={{ position: "fixed", top: 16, right: 16, display: "grid", gap: 8, zIndex: 1000 }}>
        {toasts.map((t) => (
          <>
          <div key={t.id} style={{ background: "#111827", color: "#fff", padding: "10px 12px", borderRadius: 10, boxShadow: "0 6px 20px rgba(0,0,0,0.25)" }}>
            {t.message}
          </div>

          <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 12, padding: 12, overflowX: "auto" }}>
            <div style={{ fontWeight: 900, marginBottom: 10 }}>Breakdown theo topic</div>
            <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0, minWidth: 620 }}>
              <thead>
                <tr>
                  {["Topic", "Đúng", "Sai", "Điểm", "Nhận xét"].map((h) => (
                    <th
                      key={h}
                      style={{ textAlign: "left", padding: "10px 8px", borderBottom: "1px solid #eee", background: "#fafafa", fontSize: 13 }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {topicBreakdown.map((topic) => {
                  const isStrong = topic.percent >= 75;
                  const isWeak = topic.percent < 50;
                  return (
                    <tr
                      key={topic.topic}
                      style={{
                        background: isStrong ? "#f6ffed" : isWeak ? "#fff1f0" : "#fff",
                      }}
                    >
                      <td style={{ padding: "10px 8px", borderBottom: "1px solid #f5f5f5", fontWeight: 700 }}>{topic.topic}</td>
                      <td style={{ padding: "10px 8px", borderBottom: "1px solid #f5f5f5" }}>{topic.correct}</td>
                      <td style={{ padding: "10px 8px", borderBottom: "1px solid #f5f5f5" }}>{topic.wrong}</td>
                      <td style={{ padding: "10px 8px", borderBottom: "1px solid #f5f5f5" }}>
                        {topic.score}/{topic.max} ({topic.percent}%)
                      </td>
                      <td
                        style={{
                          padding: "10px 8px",
                          borderBottom: "1px solid #f5f5f5",
                          color: isStrong ? "#166534" : isWeak ? "#b91c1c" : "#6b7280",
                          fontWeight: 600,
                        }}
                      >
                        {topic.remark}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 12, padding: 12 }}>
            <div style={{ fontWeight: 900, marginBottom: 10 }}>Breakdown theo độ khó</div>
            {[ ["easy", "Dễ"], ["medium", "Trung bình"], ["hard", "Khó"] ].map(([name, label]) => {
              const stats = difficultyStats[name];
              const pct = stats.total > 0 ? Math.round((stats.correct / stats.total) * 100) : 0;
              return (
                <div key={name} style={{ marginBottom: 10 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span>{label}</span>
                    <span>{stats.correct}/{stats.total} ({pct}%)</span>
                  </div>
                  <div style={{ height: 10, borderRadius: 999, background: "#f0f0f0", overflow: "hidden" }}>
                    <div style={{ height: 10, width: `${pct}%`, background: pct >= 70 ? "#52c41a" : pct >= 40 ? "#faad14" : "#ff4d4f" }} />
                  </div>
                </div>
              );
            })}
            {!!weakestTopic && (
              <button
                style={{ marginTop: 8, padding: "8px 12px" }}
                onClick={() => navigate(`/learning-path?topic=${encodeURIComponent(weakestTopic)}`)}
              >
                Ôn lại topic yếu: {weakestTopic}
              </button>
            )}
          </div>

          <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 12, padding: 12 }}>
            <div style={{ fontWeight: 900, marginBottom: 8 }}>AI Recommendation</div>
            {recLoading ? (
              <div style={{ color: "#666" }}>Đang lấy gợi ý từ AI…</div>
            ) : recError ? (
              <div style={{ color: "#b91c1c" }}>{recError}</div>
            ) : (
              <>
                <div style={{ color: "#333" }}>
                  Dựa trên kết quả, AI đề xuất bạn tập trung vào:{" "}
                  <b>{recommendedTopics.length ? recommendedTopics.join(", ") : "các topic có tỷ lệ đúng thấp."}</b>
                </div>
                <button
                  style={{ marginTop: 10, padding: "10px 14px", fontWeight: 700 }}
                  onClick={() => navigate("/learning-path")}
                >
                  Bắt đầu học theo lộ trình được đề xuất →
                </button>
              </>
            )}
          </div>

          <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 12, padding: 12 }}>
            <div style={{ fontWeight: 900, marginBottom: 8 }}>Đáp án & giải thích chi tiết</div>

            <div style={{ display: "grid", gap: 12 }}>
              {(result.answer_review || result.breakdown || []).map((b, i) => {
                const q = qMap[b.question_id];
                const isMcq = typeof b.correct_answer_index !== "undefined" || (b.type || "").toLowerCase() === "mcq";
                const isEssay = !isMcq;

                return (
                  <div
                    key={`${b.question_id}_${i}`}
                    style={{
                      border: `1px solid ${b.is_correct ? "#b7eb8f" : "#ffccc7"}`,
                      borderRadius: 12,
                      padding: 12,
                      background: b.is_correct ? "#f6ffed" : "#fff2f0",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                      <div style={{ fontWeight: 800 }}>{b.is_correct ? "✅" : "❌"} Câu {i + 1}</div>
                      <div style={{ color: "#333" }}>
                        <b>{b.score_points ?? 0}</b> / <b>{b.max_points ?? (isMcq ? 1 : q?.max_points ?? 10)}</b>
                      </div>
                    </div>

                    <div style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{q?.stem || "(Không có nội dung câu hỏi)"}</div>

                    {isMcq && (
                      <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
                        {(q?.options || []).map((op, idx2) => {
                          const chosen = Number(b.your_answer_index ?? b.chosen);
                          const correct = Number(b.correct_answer_index ?? b.correct);
                          const chosenThis = chosen === idx2;
                          const correctThis = correct === idx2;

                          const bg = correctThis
                            ? "#f6ffed"
                            : chosenThis && !correctThis
                              ? "#fff2f0"
                              : "#fff";

                          const border = correctThis
                            ? "1px solid #b7eb8f"
                            : chosenThis && !correctThis
                              ? "1px solid #ffccc7"
                              : "1px solid #eee";

                          return (
                            <div key={idx2} style={{ border, background: bg, borderRadius: 10, padding: "8px 10px" }}>
                              <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                                <div style={{ width: 22, fontWeight: 800 }}>{String.fromCharCode(65 + idx2)}.</div>
                                <div style={{ flex: 1 }}>{op}</div>
                                <div style={{ width: 110, textAlign: "right", fontSize: 13, color: "#555" }}>
                                  {correctThis ? "✅ Đáp án" : chosenThis ? "🧑‍🎓 Bạn chọn" : ""}
                                </div>
                              </div>
                            </div>
                          );
                        })}

                        <div
                          style={{
                            marginTop: 6,
                            padding: 10,
                            borderRadius: 12,
                            background: b.is_correct ? "#f6ffed" : "#fff2f0",
                            border: b.is_correct ? "1px solid #b7eb8f" : "1px solid #ffccc7",
                          }}
                        >
                          <div style={{ fontWeight: 900 }}>{b.is_correct ? "✅ Chính xác" : "❌ Chưa đúng"}</div>
                          {!b.is_correct && (
                            <details style={{ marginTop: 8 }}>
                              <summary style={{ cursor: "pointer", fontWeight: 700 }}>💡 Xem giải thích</summary>
                              <div style={{ marginTop: 6, whiteSpace: "pre-wrap", color: "#333" }}>
                                <b>Giải thích:</b>{" "}
                                {b.explanation || explanationsByQuestion?.[String(b.question_id)] || (explanationsLoading ? "Đang tải..." : "(Chưa có giải thích)")}
                              </div>
                            </details>
                          )}
                          {b.key_concept ? (
                            <div style={{ marginTop: 4, color: "#555" }}>
                              <b>Khái niệm chính:</b> {b.key_concept}
                            </div>
                          ) : null}
                          {!b.is_correct && (
                            <div style={{ marginTop: 6, color: "#333" }}>
                              Bạn chọn: <b>{Number.isInteger(b.your_answer_index) && b.your_answer_index >= 0 ? String.fromCharCode(65 + Number(b.your_answer_index)) : "(không chọn)"}</b>
                              {" · "}
                              Đáp án đúng: <b>{Number.isInteger(b.correct_answer_index) && b.correct_answer_index >= 0 ? String.fromCharCode(65 + Number(b.correct_answer_index)) : "?"}</b>
                            </div>
                          )}
                          <button
                            type="button"
                            style={{ marginTop: 8, padding: "6px 10px", borderRadius: 8, border: "1px solid #d9d9d9", background: "#fff", cursor: "pointer" }}
                            onClick={() => {
                              const stem = q?.stem || b?.stem || "";
                              navigate(`/tutor?question=${encodeURIComponent(stem)}`);
                            }}
                          >
                            Hỏi Tutor
                          </button>
                          {renderSources(b.sources)}
                        </div>
                      </div>
                    )}

                    {isEssay && (
                      <div style={{ marginTop: 10 }}>
                        <div style={{ fontWeight: 800, marginBottom: 6 }}>Bài làm của bạn</div>
                        <div
                          style={{
                            whiteSpace: "pre-wrap",
                            background: "#fff",
                            border: "1px solid #eee",
                            borderRadius: 12,
                            padding: 10,
                          }}
                        >
                          {b.your_answer || b.answer_text || "(Bạn chưa nhập câu trả lời)"}
                        </div>

                        <details style={{ marginTop: 10 }}>
                          <summary style={{ cursor: "pointer", fontWeight: 700 }}>Xem giải thích chi tiết</summary>
                          <div
                            style={{
                              marginTop: 10,
                              background: "#fff",
                              border: "1px solid #e6f4ff",
                              borderRadius: 12,
                              padding: 10,
                            }}
                          >
                            <div style={{ whiteSpace: "pre-wrap", color: "#333" }}>{b.explanation || "(Chưa có giải thích)"}</div>
                          </div>
                        </details>

                        {b.explanation ? (
                          <div
                            style={{
                              marginTop: 10,
                              background: "#fff",
                              border: "1px solid #e6f4ff",
                              borderRadius: 12,
                              padding: 10,
                            }}
                          >
                            <div style={{ fontWeight: 800, marginBottom: 4 }}>Gợi ý / hướng dẫn</div>
                            <div style={{ whiteSpace: "pre-wrap", color: "#333" }}>{b.explanation}</div>
                          </div>
                        ) : null}

                        <div style={{ marginTop: 10 }}>
                          <div style={{ fontWeight: 800 }}>Chấm điểm</div>
                          {!b.graded ? (
                            <div style={{ marginTop: 6, color: "#666" }}>
                              (Bài tự luận đang chờ chấm theo rubric — giáo viên hoặc AI sẽ cập nhật sau.)
                            </div>
                          ) : (
                            <>
                              <div style={{ marginTop: 6, color: "#333" }}>{b.comment || ""}</div>
                              {Array.isArray(b.rubric_breakdown) && b.rubric_breakdown.length > 0 && (
                                <details style={{ marginTop: 8 }}>
                                  <summary style={{ cursor: "pointer" }}>Xem rubric breakdown</summary>
                                  <div style={{ marginTop: 8, display: "grid", gap: 8 }}>
                                    {b.rubric_breakdown.map((rb, j) => (
                                      <div key={j} style={{ background: "#fff", border: "1px solid #eee", borderRadius: 10, padding: 10 }}>
                                        <div style={{ fontWeight: 800 }}>{rb.criterion}</div>
                                        <div style={{ marginTop: 4, color: "#333" }}>
                                          {rb.points_awarded} / {rb.max_points}
                                        </div>
                                        {rb.comment ? <div style={{ marginTop: 4, color: "#555" }}>{rb.comment}</div> : null}
                                      </div>
                                    ))}
                                  </div>
                                </details>
                              )}
                            </>
                          )}
                        </div>

                        {renderSources(b.sources)}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
          </>
        ))}
      </div>
    </div>
  );
}
