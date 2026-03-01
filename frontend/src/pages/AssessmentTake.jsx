import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";

export default function AssessmentTake() {
  const { id, quizSetId } = useParams();
  const assessmentId = Number(quizSetId || id);
  const { userId } = useAuth();
  const navigate = useNavigate();

  const [data, setData] = useState(null);
  const [answers, setAnswers] = useState({});
  const [deadlineAt, setDeadlineAt] = useState(null);
  const [timeLeftSec, setTimeLeftSec] = useState(null);
  const [attemptLocked, setAttemptLocked] = useState(false);
  const [attemptId, setAttemptId] = useState(null);
  const [serverOffsetMs, setServerOffsetMs] = useState(0);
  const [timedOutBanner, setTimedOutBanner] = useState(false);
  const [attemptLocked, setAttemptLocked] = useState(false);
  const [result, setResult] = useState(null);
  const [aiRecommendations, setAiRecommendations] = useState([]);
  const [recLoading, setRecLoading] = useState(false);
  const [recError, setRecError] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [pathAssigned, setPathAssigned] = useState(false);
  const [citationMap, setCitationMap] = useState({});

  const autoSubmittedRef = useRef(false);
  const warningShownRef = useRef({ five: false, one: false });
  const diagnosticBannerRef = useRef(null);

  const learningPathBannerRef = useRef(null);
  const answeredCount = useMemo(() => Object.keys(answers).length, [answers]);

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


  const diagnosticLevelTheme = (levelValue) => {
    const raw = String(levelValue || "").toLowerCase();
    if (["yeu", "yếu", "beginner"].some((x) => raw.includes(x))) {
      return { label: "Yếu", color: "#cf1322", bg: "#fff1f0", border: "#ffccc7" };
    }
    if (["trung", "tb", "intermediate"].some((x) => raw.includes(x))) {
      return { label: "Trung bình", color: "#ad6800", bg: "#fffbe6", border: "#ffe58f" };
    }
    if (["kha", "khá"].some((x) => raw.includes(x))) {
      return { label: "Khá", color: "#096dd9", bg: "#e6f4ff", border: "#91caff" };
    }
    if (["gioi", "giỏi", "advanced"].some((x) => raw.includes(x))) {
      return { label: "Giỏi", color: "#531dab", bg: "#f9f0ff", border: "#d3adf7" };
    }
    return { label: String(levelValue || "Chưa rõ"), color: "#595959", bg: "#fafafa", border: "#d9d9d9" };
  };

  const formatDuration = (sec) => {
    const s = Math.max(0, Math.floor(Number(sec || 0)));
    const hh = Math.floor(s / 3600);
    const mm = Math.floor((s % 3600) / 60);
    const ss = s % 60;
    if (hh > 0) return `${hh}h ${String(mm).padStart(2, "0")}m ${String(ss).padStart(2, "0")}s`;
    return `${mm}m ${String(ss).padStart(2, "0")}s`;
  };

  useEffect(() => {
    if (result?.synced_diagnostic?.stage === "pre" && result?.synced_diagnostic?.plan_id) {
      diagnosticBannerRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [result]);

  const difficultyStats = useMemo(() => {
    const buckets = {
      easy: { total: 0, correct: 0 },
      medium: { total: 0, correct: 0 },
      hard: { total: 0, correct: 0 },
    };
    for (const item of result?.answer_review || []) {
      const key = String(item?.difficulty || "medium").toLowerCase();
      if (!buckets[key]) continue;
      buckets[key].total += 1;
      if (item?.is_correct) buckets[key].correct += 1;
    }
    return buckets;
  }, [result]);

  useEffect(() => {
    if (result?.synced_diagnostic?.stage === "pre" && result?.synced_diagnostic?.plan_id) {
      learningPathBannerRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [result]);

  const groupedQuestions = useMemo(() => {
    const questions = data?.questions || [];

    const classifyByPoints = (q) => {
      const points = Number(q?.max_points || 0);
      if (points <= 2) return "easy";
      if (points <= 5) return "medium";
      return "hard";
    };

    const classify = (q) => {
      const bloom = String(q?.bloom_level || "").toLowerCase();

      if (["remember", "understand"].includes(bloom)) return "easy";
      if (["apply", "analyze"].includes(bloom)) return "medium";
      if (["evaluate", "create"].includes(bloom) || q?.type === "essay") return "hard";

      return classifyByPoints(q);
    };

    const easy = [];
    const medium = [];
    const hard = [];

    for (const q of questions) {
      const bucket = classify(q);
      if (bucket === "easy") easy.push(q);
      else if (bucket === "medium") medium.push(q);
      else hard.push(q);
    }

    return { easy, medium, hard };
  }, [data]);


  const detectDifficulty = (q) => {
    const bloom = String(q?.bloom_level || "").toLowerCase();
    if (["remember", "understand"].includes(bloom)) return "Easy";
    if (["apply", "analyze"].includes(bloom)) return "Medium";
    if (["evaluate", "create"].includes(bloom) || q?.type === "essay") return "Hard";
    return "Medium";
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

  const load = async () => {
    setLoading(true);
    setError("");
    setResult(null);
    setAiRecommendations([]);
    setRecError("");
    setRecLoading(false);
    setPathAssigned(false);
    autoSubmittedRef.current = false;
    try {
      const d = await apiJson(`/assessments/${assessmentId}`, { method: "GET" });
      setData(d);
      setAnswers({});
      setAttemptId(null);
      setAttemptLocked(false);
      setTimedOutBanner(false);
      setAttemptLocked(false);
      warningShownRef.current = { five: false, one: false };

      const session = await apiJson(`/attempts/start`, {
        method: "POST",
        body: { quiz_id: Number(d?.assessment_id || assessmentId), student_id: Number(userId ?? 0) },
      });
      setAttemptId(Number(session?.attempt_id || 0) || null);

      const currentAttemptId = Number(session?.attempt_id || 0) || null;
      setAttemptId(currentAttemptId);

      const startedAttemptId = Number(session?.attempt_id || 0) || null;
      if (startedAttemptId) {
        try {
          const timer = await apiJson(`/attempts/${startedAttemptId}/timer-status`, { method: "GET" });
          setTimeLeftSec(Number(timer?.remaining_seconds ?? timer?.time_left_seconds ?? 0));
          setAttemptLocked(Boolean(timer?.locked));
          setDeadlineAt(null);
        } catch {
          const secs = Number(session?.duration_seconds || session?.time_limit_seconds || 0);
          setDeadlineAt(null);
          setTimeLeftSec(Number.isFinite(secs) && secs > 0 ? secs : null);
        }
      const serverNowMs = Date.parse(session?.server_time || "");
      const offsetMs = Number.isFinite(serverNowMs) && serverNowMs > 0 ? serverNowMs - Date.now() : 0;
      setServerOffsetMs(offsetMs);

      const deadlineMs = Date.parse(session?.deadline_utc || "");
      if (Number.isFinite(deadlineMs) && deadlineMs > 0) {
        setDeadlineAt(deadlineMs);
        setTimeLeftSec(Math.max(0, Math.floor((deadlineMs - (Date.now() + offsetMs)) / 1000)));
      } else {
        setDeadlineAt(null);
        const secs = Number(session?.duration_seconds || 0);

        const secs = Number(session?.remaining_seconds ?? session?.duration_seconds || 0);
        setTimeLeftSec(Number.isFinite(secs) && secs > 0 ? secs : null);
      }
    } catch (e) {
      setError(e?.message || "Không load được bài tổng hợp");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (Number.isFinite(assessmentId)) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assessmentId]);

  // Server-synced countdown timer tick
  useEffect(() => {
    if (timeLeftSec == null) return;
    if (result) return;
    if (submitting) return;
    if (attemptLocked) return;
    if (timeLeftSec == null || result || submitting) return;

    const t = setInterval(() => {
      if (deadlineAt) {
        setTimeLeftSec(Math.max(0, Math.floor((deadlineAt - (Date.now() + serverOffsetMs)) / 1000)));
        return;
      }
      setTimeLeftSec((prev) => {
        if (prev == null) return prev;
        return Math.max(0, prev - 1);
      });
    }, 1000);

    return () => clearInterval(t);
  }, [timeLeftSec == null, result, submitting, deadlineAt, attemptLocked]);
  }, [timeLeftSec == null, result, submitting]);
  }, [timeLeftSec == null, result, submitting, deadlineAt, serverOffsetMs]);


  useEffect(() => {
    if (!attemptId || result || submitting) return;

    const poll = async () => {
      try {
        const status = await apiJson(`/attempts/${attemptId}/status`, { method: "GET" });
        const serverNowMs = Date.parse(status?.server_time || "");
        const offsetMs = Number.isFinite(serverNowMs) && serverNowMs > 0 ? serverNowMs - Date.now() : serverOffsetMs;
        setServerOffsetMs(offsetMs);

        const deadlineMs = Date.parse(status?.deadline || "");
        if (Number.isFinite(deadlineMs) && deadlineMs > 0) {
          setDeadlineAt(deadlineMs);
          setTimeLeftSec(Math.max(0, Math.floor((deadlineMs - (Date.now() + offsetMs)) / 1000)));
        } else {
          const remaining = Number(status?.remaining_seconds);
          if (Number.isFinite(remaining)) {
            setTimeLeftSec(Math.max(0, Math.floor(remaining)));
          }
        }
      } catch {
        // keep local countdown when status endpoint is temporarily unavailable.
      }
    };

    poll();
    const t = setInterval(poll, 15000);
    return () => clearInterval(t);
  }, [attemptId, result, submitting, serverOffsetMs]);

  useEffect(() => {
    if (timeLeftSec == null || result || submitting) return;
    if (timeLeftSec <= 300 && !warningShownRef.current.five) {
      warningShownRef.current.five = true;
      setError("Cảnh báo: còn 5 phút để hoàn thành bài.");
      return;
    }
    if (timeLeftSec <= 60 && !warningShownRef.current.one) {
      warningShownRef.current.one = true;
      setError("Cảnh báo: chỉ còn 1 phút! Hãy kiểm tra và nộp bài.");
    }
  }, [timeLeftSec, result, submitting]);

  // Heartbeat every 30s: autosave + lock sync from server truth.
  useEffect(() => {
    if (timeLeftSec !== 0 && !attemptLocked) return;
    if (result) return;
    if (submitting) return;
    if (autoSubmittedRef.current) return;
    autoSubmittedRef.current = true;
    submit(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeLeftSec, result, submitting]);
    if (!attemptId || result || submitting || !data?.questions?.length) return;

    const buildAnswers = () =>
      (data.questions || []).map((q) => ({
        question_id: q.question_id,
        answer_index: answers[q.question_id]?.answer_index ?? null,
        answer_text: answers[q.question_id]?.answer_text ?? null,
      }));

    const sendHeartbeat = async () => {
      try {
        const hb = await apiJson(`/attempts/${attemptId}/heartbeat`, {
          method: "POST",
          body: { answers: buildAnswers() },
        });

        if (Number.isFinite(Number(hb?.time_left_seconds))) {
          setTimeLeftSec(Math.max(0, Number(hb.time_left_seconds)));
        }

        if (hb?.locked) {
          setAttemptLocked(true);
          if (!autoSubmittedRef.current) {
            autoSubmittedRef.current = true;
            setTimedOutBanner(true);
            setError("Hết giờ, hệ thống đã khóa bài và đang tự nộp.");
            submit(true);
          }
        }
      } catch {
        // keep UI timer; heartbeat sẽ thử lại ở lần sau
      }
    };

    sendHeartbeat();
    const hbTimer = setInterval(sendHeartbeat, 30000);
    return () => clearInterval(hbTimer);
  }, [attemptId, answers, data?.questions, result, submitting]);

  const setMcq = (qid, idx) => {
    setAnswers((prev) => ({ ...prev, [qid]: { ...(prev[qid] || {}), answer_index: idx } }));
  };

  const setEssay = (qid, txt) => {
    setAnswers((prev) => ({ ...prev, [qid]: { ...(prev[qid] || {}), answer_text: txt } }));
  };

  useEffect(() => {
    if (!attemptId || result || submitting) return undefined;

    const buildAnswerList = () => (data?.questions || []).map((q) => ({
      question_id: q.question_id,
      answer_index: answers[q.question_id]?.answer_index ?? null,
      answer_text: answers[q.question_id]?.answer_text ?? null,
    }));

    const tick = async () => {
      try {
        const hb = await apiJson(`/attempts/${attemptId}/heartbeat`, {
          method: "POST",
          body: { answers: buildAnswerList() },
        });
        const nextLeft = Number(hb?.time_left_seconds ?? 0);
        if (Number.isFinite(nextLeft)) setTimeLeftSec(nextLeft);
        setAttemptLocked(Boolean(hb?.locked));
      } catch {
        // keep local countdown as fallback
      }
    };

    tick();
    const id = setInterval(tick, 30000);
    return () => clearInterval(id);
  }, [attemptId, result, submitting, data, answers]);


  const submit = async (auto = false) => {
    if (!data?.assessment_id) return;
    setSubmitting(true);
    setError("");

    try {
      const answerList = (data.questions || []).map((q) => ({
        question_id: q.question_id,
        answer_index: answers[q.question_id]?.answer_index ?? null,
        answer_text: answers[q.question_id]?.answer_text ?? null,
      }));

      let r = null;
      if (attemptId) {
        r = await apiJson(`/attempts/${attemptId}/submit`, {
          method: "POST",
          body: { answers: answerList, force: Boolean(auto) },
        });
      } else {
        r = await apiJson(`/assessments/quiz-sets/${data.assessment_id}/submit`, {
          method: "POST",
          body: {
            user_id: Number(userId ?? 1),
            answers: answerList,
          },
        });
      if (!attemptId) {
        throw new Error("Không tìm thấy attempt để nộp bài.");

        throw new Error("Không tìm thấy attempt hợp lệ. Vui lòng tải lại bài làm.");
      }
      const r = await apiJson(`/attempts/${attemptId}/submit`, {
        method: "POST",
        body: { answers: answerList },
      });

      const r = await apiJson(`/attempts/${attemptId}/submit`, {
        method: "POST",
        body: { answers: answerList },
      });

      setResult(r);
      setTimedOutBanner(Boolean(auto || r?.timed_out || r?.locked));
      setAttemptLocked(Boolean(r?.locked));

      const attemptId = r?.attempt_id || r?.attemptId || r?.assessment_attempt_id;
      if (attemptId) {
        setRecLoading(true);
        setRecError("");
        try {
          const rec = await apiJson(`/v1/assessments/${attemptId}/recommendations`, { method: "GET" });
          setAiRecommendations(rec || []);
        } catch (recErr) {
          setRecError(recErr?.message || "Không tải được AI recommendation");
          setAiRecommendations([]);
        } finally {
          setRecLoading(false);
        }
      }

      const isEntryTest = String(r?.assessment_kind || data?.kind || "").toLowerCase() === "diagnostic_pre";
      if (isEntryTest) {
        setPathAssigned(Boolean(r?.learning_plan_created));
      }

      if (auto || r?.timed_out) {
        setError("Hết giờ, hệ thống đã tự nộp");
      }
    } catch (e) {
      setError(e?.message || "Submit thất bại");
    } finally {
      setSubmitting(false);
    }
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

  if (result) {
    return (
      <div style={{ maxWidth: 980, margin: "0 auto", padding: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
          <Link to="/assessments" style={{ textDecoration: "none" }}>
            <button style={{ padding: "8px 12px" }}>⬅ Danh sách</button>
          </Link>
          <button onClick={load} style={{ padding: "8px 12px" }}>Làm lại</button>
        </div>
        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12, padding: 16 }}>
          <h3 style={{ marginTop: 0 }}>Kết quả</h3>
          <div>Điểm: <b>{Math.round(Number(result?.total_score_percent ?? result?.score_percent ?? 0))}/100</b></div>
          <div>Đúng: {Number(result?.correct_count ?? 0)} / {Number(result?.total_questions ?? data?.questions?.length || 0)}</div>
          {Number(result?.time_spent_seconds || 0) > 0 && (
            <div>Thời gian làm bài: {fmtTime(Number(result?.time_spent_seconds || 0))}</div>
          )}
          {Number(result?.duration_seconds || 0) > 0 && (
            <div>Giới hạn thời gian: {fmtTime(Number(result?.duration_seconds || 0))}</div>
          )}
        </div>
        {pathAssigned && (
          <div style={{ marginTop: 12, padding: 10, borderRadius: 10, background: "#fffbe6", border: "1px solid #ffe58f" }}>
            🎯 Dựa trên kết quả, hệ thống đã tạo lộ trình học tập phù hợp cho bạn!
          </div>
        )}
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>{data?.title || "Bài tổng hợp"}</h2>
          <div style={{ color: "#666" }}>
            Level: <b>{data?.level}</b> {data?.kind ? <span>• Kind: <b>{data.kind}</b></span> : null}
          </div>
          {(String(data?.kind || "").toLowerCase() === "diagnostic_pre" || String(data?.metadata?.type || "").toLowerCase() === "diagnostic") ? (
            <div style={{ marginTop: 8, display: "inline-block", background: "#e6f4ff", color: "#0958d9", border: "1px solid #91caff", borderRadius: 999, padding: "4px 10px", fontWeight: 800 }}>
              ĐÂY LÀ BÀI KIỂM TRA ĐẦU VÀO
            </div>
          ) : null}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Link to="/assessments" style={{ textDecoration: "none" }}>
            <button style={{ padding: "8px 12px" }}>⬅ Danh sách</button>
          </Link>
          <button onClick={load} style={{ padding: "8px 12px" }}>
            Làm lại
          </button>
        </div>
      </div>

      {attemptLocked && !result && (
        <div style={{ marginTop: 12, background: "#fff1f0", border: "1px solid #ffccc7", padding: 12, borderRadius: 12, color: "#a8071a", fontWeight: 700 }}>
          Bài làm đã bị khóa do hết thời gian. Hệ thống sẽ tự nộp bài.
        </div>
      )}

      {timedOutBanner && (
        <div style={{ marginTop: 12, background: "#fff1f0", border: "1px solid #ffccc7", padding: 12, borderRadius: 12, color: "#a8071a", fontWeight: 700 }}>
          Hết giờ, hệ thống đã tự nộp
        </div>
      )}

      {timeLimitSec > 0 && (
        <div
          style={{
            marginTop: 12,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 12,
            background: "#fff",
            border: "1px solid #eee",
            borderRadius: 14,
            padding: 12,
            boxShadow: "0 2px 10px rgba(0,0,0,0.04)",
          }}
        >
          <div>
            <div style={{ fontWeight: 800, fontSize: 16 }}>⏱ Thời gian còn lại: {fmtTime(timeLeftSec)}</div>
            <div style={{ color: "#666", fontSize: 13 }}>
              (Tổng thời gian gợi ý bởi AI: {Math.round(timeLimitSec / 60)} phút)
            </div>
          </div>
          <div style={{ minWidth: 220 }}>
            <div
              style={{
                height: 10,
                background: "#f0f0f0",
                borderRadius: 999,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  height: 10,
                  width: `${Math.min(100, Math.max(0, (timeLeftSec / timeLimitSec) * 100))}%`,
                  background: timeLeftSec <= 60 ? "#ff4d4f" : "#52c41a",
                }}
              />
            </div>
            <div style={{ marginTop: 6, color: "#666", fontSize: 13, textAlign: "right" }}>
              {answeredCount}/{data?.questions?.length || 0} câu đã chọn
            </div>
          </div>
        </div>
      )}

      {error && (
        <div style={{ marginTop: 12, background: "#fff3f3", border: "1px solid #ffd0d0", padding: 12, borderRadius: 12 }}>
          {error}
        </div>
      )}

      {timeLimitSec <= 0 && (
        <div style={{ marginTop: 12, color: "#666" }}>Đã trả lời: {answeredCount}/{data?.questions?.length || 0}</div>
      )}

      <div
        style={{
          position: "sticky",
          top: 8,
          zIndex: 5,
          marginTop: 12,
          background: "#fff",
          border: "1px solid #eee",
          borderRadius: 10,
          padding: "8px 12px",
          display: "flex",
          flexWrap: "wrap",
          gap: 12,
        }}
      >
        <a href={`#${sectionMeta.easy.id}`} style={{ color: sectionMeta.easy.color, fontWeight: 700, textDecoration: "none" }}>
          {sectionMeta.easy.label} ({sectionMeta.easy.questions.length})
        </a>
        <a href={`#${sectionMeta.medium.id}`} style={{ color: sectionMeta.medium.color, fontWeight: 700, textDecoration: "none" }}>
          {sectionMeta.medium.label} ({sectionMeta.medium.questions.length})
        </a>
        <a href={`#${sectionMeta.hard.id}`} style={{ color: sectionMeta.hard.color, fontWeight: 700, textDecoration: "none" }}>
          {sectionMeta.hard.label} ({sectionMeta.hard.questions.length})
        </a>
      </div>

      <div style={{ display: "grid", gap: 14, marginTop: 12 }}>
        {[
          ["easy", sectionMeta.easy],
          ["medium", sectionMeta.medium],
          ["hard", sectionMeta.hard],
        ].map(([sectionKey, section]) => (
          <div key={sectionKey} id={section.id}>
            <div
              className={`section-header ${section.className}`}
              style={{
                background: section.bg,
                border: `1px solid ${section.color}`,
                color: section.color,
                borderRadius: 4,
                padding: "8px 12px",
                margin: "16px 0",
                fontWeight: 800,
                display: "flex",
                justifyContent: "space-between",
                flexWrap: "wrap",
                gap: 8,
              }}
            >
              <span>{section.title} ({section.questions.length} câu)</span>
              <span>{section.label}</span>
            </div>

            <div style={{ display: "grid", gap: 14 }}>
              {section.questions.map((q) => {
                const orderNo = (data?.questions || []).findIndex((it) => it.question_id === q.question_id) + 1;
                return renderQuestionCard(q, orderNo);
              })}
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 16, display: "flex", gap: 10, alignItems: "center" }}>
        <button onClick={() => submit(false)} disabled={submitting || !!result || attemptLocked} style={{ padding: "10px 14px" }}>
          Nộp bài
        </button>
        {submitting && <span style={{ color: "#666" }}>Đang nộp…</span>}
      </div>

      {result && (
        <div style={{ marginTop: 16, display: "grid", gap: 14 }}>
          <div
            style={{
              background: "#fff",
              border: "1px solid #e5e7eb",
              padding: 12,
              borderRadius: 12,
            }}
          >
            <div style={{ fontWeight: 800, fontSize: 16 }}>✅ Nộp bài thành công</div>
            <div
              style={{
                marginTop: 10,
                background: scoreTheme.bg,
                border: `1px solid ${scoreTheme.track}`,
                borderRadius: 12,
                padding: 12,
                display: "flex",
                flexWrap: "wrap",
                gap: 14,
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <div>
                <div style={{ fontSize: 13, color: "#666" }}>Tổng điểm</div>
                <div
                  style={{
                    marginTop: 2,
                    fontWeight: 900,
                    fontSize: 30,
                    color: scoreTheme.color,
                  }}
                >
                  {resolvedScore}/100 – {levelLabel(resolvedScore)}
                </div>
              </div>
              <div style={{ minWidth: 220, flex: 1 }}>
                <div style={{ height: 12, borderRadius: 999, background: "#f3f4f6", overflow: "hidden" }}>
                  <div
                    style={{
                      height: 12,
                      width: `${Math.min(100, Math.max(0, resolvedScore))}%`,
                      background: scoreTheme.color,
                    }}
                  />
                </div>
                <div style={{ marginTop: 8, display: "flex", justifyContent: "space-between", fontSize: 13, color: "#555" }}>
                  <span>Level: <b>{scoreTheme.label}</b></span>
                  <span>⏱️ {formatDuration(result.duration_sec ?? 0)}</span>
                </div>
              </div>
            </div>
            <div style={{ marginTop: 6, display: "flex", flexWrap: "wrap", gap: 10, color: "#333" }}>
              <span>
                Trắc nghiệm: <b>{result.mcq_score_percent ?? result.score_percent}%</b>
              </span>
              <span>
                Tự luận: <b>{result.essay_score_percent ?? 0}%</b>
              </span>
              <span>
                Tổng: <b>{result.total_score_percent ?? result.score_percent}%</b>
              </span>
              <span style={{ color: "#555" }}>{result.status}</span>
            </div>

            {result?.student_level ? (
              <div style={{ marginTop: 8, color: "#0958d9" }}>
                Phân loại trình độ: <b>{result.student_level}</b>
              </div>
            ) : null}

            {pathAssigned && (
              <div style={{ marginTop: 10, padding: 10, borderRadius: 10, background: "#fffbe6", border: "1px solid #ffe58f" }}>
                🎯 Dựa trên kết quả, hệ thống đã tạo lộ trình học tập phù hợp cho bạn!
              </div>
            )}

            {result?.synced_diagnostic?.stage === "pre" && (
              <div
                ref={diagnosticBannerRef}
                ref={learningPathBannerRef}
                style={{
                  marginTop: 10,
                  background: "#fff",
                  border: "1px solid #b7eb8f",
                  borderRadius: 12,
                  padding: 12,
                }}
              >
                <div style={{ fontWeight: 800 }}>🎯 Placement test đã cập nhật trình độ</div>
                <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ color: "#333" }}>Level:</span>
                <div style={{ marginTop: 6, color: "#333", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span>Level mới:</span>
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      padding: "2px 10px",
                      borderRadius: 999,
                      fontSize: 12,
                      fontWeight: 700,
                      color: diagnosticLevelTheme(result?.synced_diagnostic?.level).color,
                      background: diagnosticLevelTheme(result?.synced_diagnostic?.level).bg,
                      border: `1px solid ${diagnosticLevelTheme(result?.synced_diagnostic?.level).border}`,
                    }}
                  >
                    {diagnosticLevelTheme(result?.synced_diagnostic?.level).label}
                      fontWeight: 700,
                      fontSize: 13,
                      border: `1px solid ${levelBadgeTheme(result.synced_diagnostic.level).border}`,
                      color: levelBadgeTheme(result.synced_diagnostic.level).color,
                      background: levelBadgeTheme(result.synced_diagnostic.level).bg,
                    }}
                  >
                    {result.synced_diagnostic.level || "Chưa xác định"}
                  </span>
                </div>
                {result.synced_diagnostic.teacher_topic ? (
                  <div style={{ marginTop: 4, color: "#666" }}>
                    Chủ đề: <b>{result.synced_diagnostic.teacher_topic}</b>
                  </div>
                ) : null}
                {result.synced_diagnostic.plan_id ? (
                  <div style={{ marginTop: 8 }}>
                    <div style={{ fontWeight: 700, color: "#237804" }}>✅ AI đã tạo lộ trình 7 ngày phù hợp với bạn</div>
                    <div style={{ marginTop: 8 }}>
                      <button style={{ padding: "8px 12px", cursor: "pointer" }} onClick={() => navigate("/learning-path")}>
                    <div style={{ fontWeight: 700, color: "#166534" }}>✅ AI đã tạo lộ trình 7 ngày phù hợp với bạn</div>
                    <div style={{ marginTop: 8 }}>
                      <button style={{ padding: "8px 12px" }} onClick={() => navigate('/learning-path')}>
                        Xem Learning Path
                      </button>
                    </div>
                  </div>
                ) : (
                  <div style={{ marginTop: 8, color: "#666" }}>
                    (Chưa tạo được Learning Path tự động — bạn vẫn có thể vào Learning Path để tạo.)
                  </div>
                )}
              </div>
            )}

            {String(result?.assessment_kind || data?.kind || "").toLowerCase() === "final_exam" && (
              <div
                style={{
                  marginTop: 10,
                  background: "#f9fafb",
                  border: "1px solid #e5e7eb",
                  borderRadius: 12,
                  padding: 12,
                }}
              >
                <div style={{ fontWeight: 800, marginBottom: 6 }}>So sánh với điểm đầu vào</div>
                {typeof result?.improvement_vs_entry !== "number" ? (
                  <div style={{ color: "#666" }}>Chưa có dữ liệu điểm đầu vào để so sánh.</div>
                ) : (
                  <>
                    <div>
                      Điểm cuối kỳ của bạn <b>{result.improvement_vs_entry >= 0 ? "tăng" : "giảm"}</b>
                      {" "}<b style={{ color: result.improvement_vs_entry >= 0 ? "#389e0d" : "#cf1322" }}>{Math.abs(result.improvement_vs_entry)} điểm</b>{" "}
                      so với bài đầu vào.
                    </div>
                    {!!result?.topics_improved?.length && (
                      <div style={{ marginTop: 6, color: "#166534" }}>
                        Topic tiến bộ: <b>{result.topics_improved.join(", ")}</b>
                      </div>
                    )}
                    {!!result?.topics_declined?.length && (
                      <div style={{ marginTop: 4, color: "#b91c1c" }}>
                        Topic cần củng cố thêm: <b>{result.topics_declined.join(", ")}</b>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}
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
                          <div style={{ marginTop: 6, whiteSpace: "pre-wrap", color: "#333" }}>
                            <b>Giải thích:</b> {b.explanation || "(Chưa có giải thích)"}
                          </div>
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
        </div>
      )}
    </div>
  );
}
