import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import StudentLevelBadge from "../components/StudentLevelBadge";
import ProgressComparison from "../components/ProgressComparison";

function MarkdownLite({ text }) {
  const blocks = useMemo(() => {
    const src = String(text || "").replace(/\r\n/g, "\n");
    if (!src.trim()) return [];
    const lines = src.split("\n");

    const out = [];
    let i = 0;

    const isUl = (l) => /^-\s+/.test(l);
    const isOl = (l) => /^\d+[.)]\s+/.test(l);
    const isH1 = (l) => /^#\s+/.test(l);
    const isH2 = (l) => /^##\s+/.test(l);
    const isH3 = (l) => /^###\s+/.test(l);

    while (i < lines.length) {
      const line = lines[i] || "";
      if (!line.trim()) {
        i += 1;
        continue;
      }

      if (isH1(line)) {
        out.push({ type: "h1", text: line.replace(/^#\s+/, "").trim() });
        i += 1;
        continue;
      }
      if (isH2(line)) {
        out.push({ type: "h2", text: line.replace(/^##\s+/, "").trim() });
        i += 1;
        continue;
      }
      if (isH3(line)) {
        out.push({ type: "h3", text: line.replace(/^###\s+/, "").trim() });
        i += 1;
        continue;
      }

      if (isUl(line)) {
        const items = [];
        while (i < lines.length && isUl(lines[i] || "")) {
          items.push(String(lines[i]).replace(/^-\s+/, "").trim());
          i += 1;
        }
        out.push({ type: "ul", items });
        continue;
      }

      if (isOl(line)) {
        const items = [];
        while (i < lines.length && isOl(lines[i] || "")) {
          items.push(String(lines[i]).replace(/^\d+[.)]\s+/, "").trim());
          i += 1;
        }
        out.push({ type: "ol", items });
        continue;
      }

      const para = [];
      while (
        i < lines.length &&
        (lines[i] || "").trim() &&
        !isH1(lines[i] || "") &&
        !isH2(lines[i] || "") &&
        !isH3(lines[i] || "") &&
        !isUl(lines[i] || "") &&
        !isOl(lines[i] || "")
      ) {
        para.push(lines[i]);
        i += 1;
      }
      out.push({ type: "p", text: para.join("\n") });
    }

    return out;
  }, [text]);

  if (!text || !String(text).trim()) return null;

  return (
    <div style={{ lineHeight: 1.65, fontSize: 15 }}>
      {blocks.map((b, idx) => {
        if (b.type === "h1") return <h2 key={idx} style={{ margin: "10px 0" }}>{b.text}</h2>;
        if (b.type === "h2") return <h3 key={idx} style={{ margin: "10px 0" }}>{b.text}</h3>;
        if (b.type === "h3") return <h4 key={idx} style={{ margin: "10px 0" }}>{b.text}</h4>;
        if (b.type === "ul") {
          return (
            <ul key={idx} style={{ margin: "8px 0 8px 20px" }}>
              {(b.items || []).map((it, j) => (
                <li key={j} style={{ margin: "4px 0" }}>{it}</li>
              ))}
            </ul>
          );
        }
        if (b.type === "ol") {
          return (
            <ol key={idx} style={{ margin: "8px 0 8px 20px" }}>
              {(b.items || []).map((it, j) => (
                <li key={j} style={{ margin: "4px 0" }}>{it}</li>
              ))}
            </ol>
          );
        }
        return (
          <p key={idx} style={{ margin: "8px 0", whiteSpace: "pre-wrap" }}>
            {b.text}
          </p>
        );
      })}
    </div>
  );
}

function ScorePill({ score, max }) {
  const s = Number.isFinite(score) ? score : 0;
  const m = Number.isFinite(max) && max > 0 ? max : 0;
  const pct = m > 0 ? Math.round((s / m) * 100) : 0;

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 10px",
        borderRadius: 999,
        border: "1px solid #ddd",
        background: "#fafafa",
        fontSize: 13,
      }}
    >
      <strong>
        {s}/{m}đ
      </strong>
      <span style={{ color: "#666" }}>({pct}%)</span>
    </span>
  );
}

function levelFromRaw(levelRaw) {
  const level = String(levelRaw || "").toLowerCase();
  if (level.includes("yếu") || level.includes("yeu")) return { label: "Yếu", color: "red", emoji: "💪", description: "Cần hỗ trợ thêm – AI sẽ hướng dẫn từng bước", learning_approach: "Học lại từ đầu với hỗ trợ AI intensive" };
  if (level.includes("trung")) return { label: "Trung Bình", color: "orange", emoji: "📚", description: "Cần ôn tập thêm trước khi học nội dung mới", learning_approach: "Tập trung vào kiến thức nền tảng" };
  if (level.includes("giỏi") || level.includes("gioi")) return { label: "Giỏi", color: "green", emoji: "🌟", description: "Nắm vững kiến thức, sẵn sàng học nội dung nâng cao", learning_approach: "Tập trung vào bài tập khó và bài tập mở rộng" };
  return { label: "Khá", color: "blue", emoji: "⭐", description: "Hiểu cơ bản, cần củng cố một số điểm", learning_approach: "Kết hợp ôn tập kiến thức yếu và học mới" };
}



function StudentLevelBadge({ level }) {
  const meta = levelFromRaw(level?.label || level);
  return (
    <span
      style={{
        padding: "4px 10px",
        borderRadius: 999,
        color: meta.color,
        background: meta.bg,
        fontWeight: 700,
        border: `1px solid ${meta.color}22`,
      }}
    >
      {meta.label}
    </span>
  );
}

function itemTypeIcon(type) {
  if (type === "homework") return "✏️";
  if (type === "quiz") return "📝";
  return "📖";
}

function difficultyBadgeStyle(difficulty) {
  const d = String(difficulty || "medium").toLowerCase();
  if (d === "hard") return { color: "#cf1322", bg: "#fff1f0" };
  if (d === "easy") return { color: "#389e0d", bg: "#f6ffed" };
  return { color: "#0958d9", bg: "#e6f4ff" };
}

const PRACTICE_LEVELS = [
  { key: "easy", label: "Dễ", bloom: "Remember / Understand" },
  { key: "medium", label: "Trung bình", bloom: "Apply / Analyze" },
  { key: "hard", label: "Khó", bloom: "Evaluate / Create" },
];

function TopicPracticePreview({ topicId, userId, nav }) {
  const [activeLevel, setActiveLevel] = useState("easy");
  const [itemsByLevel, setItemsByLevel] = useState({ easy: [], medium: [], hard: [] });
  const [loadingByLevel, setLoadingByLevel] = useState({ easy: false, medium: false, hard: false });
  const [errorByLevel, setErrorByLevel] = useState({ easy: "", medium: "", hard: "" });

  useEffect(() => {
    if (!topicId || !userId) return;
    if ((itemsByLevel[activeLevel] || []).length > 0 || loadingByLevel[activeLevel]) return;

    (async () => {
      setLoadingByLevel((m) => ({ ...m, [activeLevel]: true }));
      setErrorByLevel((m) => ({ ...m, [activeLevel]: "" }));
      try {
        const data = await apiJson(`/quiz/by-topic?topic_id=${topicId}&level=${activeLevel}&user_id=${userId}`);
        const qs = Array.isArray(data?.questions) ? data.questions : [];
        setItemsByLevel((m) => ({ ...m, [activeLevel]: qs }));
      } catch (e) {
        setErrorByLevel((m) => ({ ...m, [activeLevel]: String(e?.message || e) }));
      } finally {
        setLoadingByLevel((m) => ({ ...m, [activeLevel]: false }));
      }
    })();
  }, [activeLevel, itemsByLevel, loadingByLevel, topicId, userId]);

  return (
    <div style={{ marginTop: 10, borderTop: "1px dashed #eee", paddingTop: 10 }}>
      <div style={{ fontWeight: 700, marginBottom: 8 }}>Bài tập luyện tập</div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {PRACTICE_LEVELS.map((lv) => (
          <button key={lv.key} type="button" onClick={() => setActiveLevel(lv.key)} style={{ border: "1px solid #dbeafe", borderRadius: 999, background: activeLevel === lv.key ? "#1d4ed8" : "#eff6ff", color: activeLevel === lv.key ? "#fff" : "#1e3a8a", padding: "4px 10px", fontSize: 13 }}>
            {lv.label}
          </button>
        ))}
      </div>

      <div style={{ marginTop: 6, color: "#666", fontSize: 12 }}>
        Bloom: {PRACTICE_LEVELS.find((x) => x.key === activeLevel)?.bloom}
      </div>

      {loadingByLevel[activeLevel] && <div style={{ color: "#666", marginTop: 6 }}>Đang tải bài tập...</div>}
      {errorByLevel[activeLevel] && <div style={{ color: "#cf1322", marginTop: 6 }}>{errorByLevel[activeLevel]}</div>}

      <ol style={{ margin: "8px 0 0 18px", padding: 0 }}>
        {(itemsByLevel[activeLevel] || []).slice(0, 5).map((q, idx) => (
          <li key={q?.question_id || idx} style={{ margin: "4px 0", color: "#334155" }}>{q?.stem}</li>
        ))}
      </ol>

      <div style={{ marginTop: 8 }}>
        <button onClick={() => nav(`/practice/${topicId}?level=${activeLevel}`)}>
          ✏️ Làm từng bài ({PRACTICE_LEVELS.find((x) => x.key === activeLevel)?.label})
        </button>
      </div>
    </div>
  );
}

function formatVNDate(dateLike) {
  if (!dateLike) return "chưa rõ ngày";
  const d = new Date(dateLike);
  if (Number.isNaN(d.getTime())) return "chưa rõ ngày";
  return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export default function LearningPath() {
  const { userId } = useAuth();
  const nav = useNavigate();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [planId, setPlanId] = useState(null);
  const [plan, setPlan] = useState(null);
  const [planDays, setPlanDays] = useState([]);
  const [selectedDay, setSelectedDay] = useState(1);

  const [taskCompletion, setTaskCompletion] = useState({});
  const [homeworkDrafts, setHomeworkDrafts] = useState({});
  const [homeworkGrades, setHomeworkGrades] = useState({});

  const [showGenerated, setShowGenerated] = useState(false);
  const [myPath, setMyPath] = useState(null);
  const [levelDetails, setLevelDetails] = useState(null);
  const [showOnlyMine, setShowOnlyMine] = useState(false);
  const [finalExam, setFinalExam] = useState(null);
  const [currentPlan, setCurrentPlan] = useState(null);
  const [planView, setPlanView] = useState("sections");
  const [comparison, setComparison] = useState(null);
  const [practiceDifficulty, setPracticeDifficulty] = useState("medium");
  const [topicProgress, setTopicProgress] = useState({});

  const currentDay = useMemo(() => {
    return (planDays || []).find((d) => Number(d.day_index) === Number(selectedDay)) || null;
  }, [planDays, selectedDay]);

  const timelineTasks = useMemo(
    () =>
      (planDays || []).flatMap((d) =>
        (d.tasks || []).map((task, idx) => ({ dayIndex: Number(d.day_index), taskIndex: idx, dayTitle: d.title, task }))
      ),
    [planDays]
  );

  const completedCount = useMemo(
    () => timelineTasks.filter((t) => taskCompletion[`${t.dayIndex}-${t.taskIndex}`]).length,
    [timelineTasks, taskCompletion]
  );

  const allDone = timelineTasks.length > 0 && completedCount === timelineTasks.length;
  const adaptiveItems = useMemo(() => (Array.isArray(currentPlan?.items) ? currentPlan.items : []), [currentPlan]);
  const groupedAdaptive = useMemo(() => ({
    study_material: adaptiveItems.filter((x) => x?.type === "study_material"),
    homework: adaptiveItems.filter((x) => x?.type === "homework"),
    quiz: adaptiveItems.filter((x) => x?.type === "quiz"),
  }), [adaptiveItems]);
  const adaptiveByDay = useMemo(() => {
    const map = {};
    adaptiveItems.forEach((it) => {
      const day = Number(it?.day || 1);
      if (!map[day]) map[day] = [];
      map[day].push(it);
    });
    return Object.entries(map).sort((a, b) => Number(a[0]) - Number(b[0]));
  }, [adaptiveItems]);
  const activeLevel = levelDetails || levelFromRaw(myPath?.student_level || plan?.student_level || "Khá");
  useEffect(() => {
    if (!userId) return;
    loadTopicProgress();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const planStats = useMemo(() => {
    const tasks = timelineTasks.map((x) => x.task || {});
    const materials = tasks.filter((t) => ["lesson", "material", "study"].includes(String(t.type || "").toLowerCase())).length || (planDays || []).length;
    const exercises = tasks.filter((t) => ["homework", "practice", "quiz", "exercise"].includes(String(t.type || "").toLowerCase())).length;
    const tests = tasks.filter((t) => ["test", "exam", "checkpoint", "final_exam"].includes(String(t.type || "").toLowerCase())).length + (finalExam ? 1 : 0);
    return { materials, exercises, tests };
  }, [timelineTasks, planDays, finalExam]);

  async function loadPersisted() {
    setLoading(true);
    setError(null);
    try {
      const cidRaw = localStorage.getItem("active_classroom_id");
      const cid = cidRaw && String(cidRaw).trim() ? Number(cidRaw) : null;
      const q = Number.isFinite(cid) && cid > 0 ? `?classroom_id=${cid}` : "";
      const lp = await apiJson(`/learning-plans/${userId}/latest${q}`);
      if (!lp || !lp.plan) {
        setPlanId(null);
        setPlan(null);
        setPlanDays([]);
        setTaskCompletion({});
        setHomeworkDrafts({});
        setHomeworkGrades({});
        return false;
      }

      setPlanId(lp.plan_id);
      setPlan(lp.plan);
      const days = (lp.plan.days || []).slice().sort((a, b) => Number(a.day_index) - Number(b.day_index));
      setPlanDays(days);
      setSelectedDay(days?.[0]?.day_index || 1);

      setTaskCompletion(lp.task_completion || {});

      const drafts = {};
      const grades = {};
      Object.entries(lp.homework_submissions || {}).forEach(([day, obj]) => {
        const di = Number(day);
        drafts[di] = { essay: obj?.answer_text || "", mcq: obj?.answer_json?.mcq_answers || {} };
        grades[di] = obj?.grade || null;
      });
      setHomeworkDrafts(drafts);
      setHomeworkGrades(grades);

      return true;
    } catch (e) {
      setError(String(e?.message || e));
      return false;
    } finally {
      setLoading(false);
    }
  }

  async function loadCurrentPlan() {
    try {
      const cidRaw = localStorage.getItem("active_classroom_id");
      const cid = cidRaw && String(cidRaw).trim() ? Number(cidRaw) : null;
      const q = Number.isFinite(cid) && cid > 0 ? `?classroom_id=${cid}` : "";
      const data = await apiJson(`/learning-plans/${userId}/current${q}`);
      setCurrentPlan(data || null);
    } catch {
      setCurrentPlan(null);
    }
  }

  async function loadEphemeral() {
    setLoading(true);
    setError(null);
    try {
      const data = await apiJson(`/profile/${userId}/learning-path?save_plan=0&with_plan=1`);
      const tp = data?.teacher_plan;
      if (!tp) {
        setPlan(null);
        setPlanDays([]);
        return;
      }
      setPlanId(null);
      setPlan(tp);
      const days = (tp.days || []).slice().sort((a, b) => Number(a.day_index) - Number(b.day_index));
      setPlanDays(days);
      setSelectedDay(days?.[0]?.day_index || 1);
      setTaskCompletion({});
      setHomeworkDrafts({});
      setHomeworkGrades({});
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  async function generateAndSavePlan() {
    setLoading(true);
    setError(null);
    setShowGenerated(false);
    try {
      await apiJson(`/profile/${userId}/learning-path?save_plan=1&with_plan=1`);
      setShowGenerated(true);
      await loadPersisted();
      await loadCurrentPlan();
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    (async () => {
      const ok = await loadPersisted();
      if (!ok) await loadEphemeral();
      await loadCurrentPlan();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  useEffect(() => {
    apiJson(`/lms/student/${userId}/my-path`)
      .then((d) => setMyPath(d?.data || null))
      .catch(() => {});
  }, [userId]);

  useEffect(() => {
    apiJson(`/v1/students/${userId}/level`)
      .then((d) => setLevelDetails(d || null))
      .catch(() => setLevelDetails(null));
    const cid = Number(localStorage.getItem("active_classroom_id"));
    if (!Number.isFinite(cid) || cid <= 0 || !userId) {
      setComparison(null);
      return;
    }
    apiJson(`/v1/students/${Number(userId)}/progress?classroomId=${cid}`)
      .then((d) => setComparison(d || null))
      .catch(() => setComparison(null));
  }, [userId]);

  useEffect(() => {
    const cidRaw = localStorage.getItem("active_classroom_id");
    const cid = Number(cidRaw);
    if (!Number.isFinite(cid) || cid <= 0) return;
    apiJson(`/classrooms/${cid}/assessments?kind=final_exam`)
      .then((d) => {
        const first = Array.isArray(d) ? d[0] : d?.items?.[0] || d?.data?.[0] || null;
        setFinalExam(first);
      })
      .catch(() => setFinalExam(null));
  }, [userId]);

  async function toggleTask(dayIndex, taskIndex, completed) {
    const key = `${dayIndex}-${taskIndex}`;
    setTaskCompletion((m) => ({ ...m, [key]: !!completed }));
    if (!planId) return;
    try {
      await apiJson(`/learning-plans/${planId}/tasks/complete`, {
        method: "POST",
        body: JSON.stringify({ user_id: userId, day_index: dayIndex, task_index: taskIndex, completed: !!completed }),
      });
      loadTopicProgress();
    } catch (e) {
      setError(String(e?.message || e));
    }
  }

  function setEssayDraft(dayIndex, value) {
    setHomeworkDrafts((prev) => ({ ...prev, [dayIndex]: { ...(prev[dayIndex] || { essay: "", mcq: {} }), essay: value } }));
  }

  function setMcqDraft(dayIndex, questionId, chosenIndex) {
    setHomeworkDrafts((prev) => {
      const day = { ...(prev[dayIndex] || { essay: "", mcq: {} }) };
      day.mcq = { ...(day.mcq || {}), [String(questionId)]: Number(chosenIndex) };
      return { ...prev, [dayIndex]: day };
    });
  }

  async function gradeHomework(dayIndex) {
    if (!planId) {
      setError("Cần lưu plan trước khi nộp bài (bấm: 'Tạo mới & lưu plan').");
      return;
    }

    const draft = homeworkDrafts?.[dayIndex] || { essay: "", mcq: {} };
    const hasMcq = Object.keys(draft.mcq || {}).length > 0;
    const hasEssay = String(draft.essay || "").trim().length > 0;
    if (!hasMcq && !hasEssay) {
      setError("Bạn chưa làm bài. Hãy chọn đáp án trắc nghiệm hoặc viết phần tự luận rồi nộp.");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const data = await apiJson(`/learning-plans/${planId}/homework/grade`, {
        method: "POST",
        body: JSON.stringify({ user_id: userId, day_index: dayIndex, answer_text: draft.essay || "", mcq_answers: draft.mcq || {} }),
      });
      setHomeworkGrades((g) => ({ ...g, [dayIndex]: data || null }));

      const dayObj = (planDays || []).find((d) => Number(d.day_index) === Number(dayIndex));
      const hwTaskIndex = (dayObj?.tasks || []).findIndex((t) => (t?.type || "").toLowerCase() === "homework");
      if (hwTaskIndex >= 0) await toggleTask(dayIndex, hwTaskIndex, true);
      else loadTopicProgress();
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }



  async function loadTopicProgress() {
    try {
      const cidRaw = localStorage.getItem("active_classroom_id");
      const cid = cidRaw && String(cidRaw).trim() ? Number(cidRaw) : null;
      const q = Number.isFinite(cid) && cid > 0 ? `?classroom_id=${cid}` : "";
      const data = await apiJson(`/lms/student/${userId}/topic-progress${q}`);
      const map = {};
      (Array.isArray(data?.topics) ? data.topics : []).forEach((row) => {
        const key = String(row?.topic || "").toLowerCase();
        if (key) map[key] = row;
      });
      setTopicProgress(map);
    } catch {
      setTopicProgress({});
    }
  }

  const assignedTopicIds = new Set((myPath?.assigned_tasks || []).map((t) => Number(t?.topic_id)).filter((v) => Number.isFinite(v)));
  const assignedTasks = Array.isArray(myPath?.plan?.assigned_tasks)
    ? myPath.plan.assigned_tasks
    : Array.isArray(myPath?.assigned_tasks)
      ? myPath.assigned_tasks
      : [];
  const weakTopics = new Set((myPath?.weak_topics || myPath?.plan?.weak_topics || []).map((t) => String(t || "").toLowerCase()));
  const progress = myPath?.progress || { completed_tasks: 0, total_tasks: assignedTasks.length, percent: 0 };
  const levelDisplay = myPath?.level || { key: activeLevel?.label, label: activeLevel?.label || "Khá", color: activeLevel?.color || "blue" };
  const pageWrap = { maxWidth: 1020, margin: "0 auto", padding: 16 };
  const card = { border: "1px solid #eee", borderRadius: 14, padding: 16, background: "#fff" };

  return (
    <div style={pageWrap}>
      <style>{`
        .timeline-item { transition: all .35s ease; }
        .timeline-item.done { transform: translateX(16px); background: #f6ffed; }
        .confetti-wrap { position: absolute; inset: 0; pointer-events: none; overflow: hidden; }
        .confetti-piece { position: absolute; width: 7px; height: 12px; opacity: .85; animation: fall 2.2s ease-out forwards; }
        @keyframes fall { 0% { transform: translateY(-20px) rotate(0deg); } 100% { transform: translateY(180px) rotate(360deg); opacity: 0; } }
      `}</style>

      {comparison ? (
        <div style={{ marginBottom: 12 }}>
          <ProgressComparison comparison={comparison} showTopics={false} />
        </div>
      ) : null}

      <div style={{ ...card, marginBottom: 12, position: "relative", overflow: "hidden" }}>
        {allDone && (
          <div className="confetti-wrap">
            {Array.from({ length: 24 }).map((_, i) => (
              <span
                key={i}
                className="confetti-piece"
                style={{ left: `${(i * 4.2) % 100}%`, animationDelay: `${(i % 8) * 0.1}s`, background: ["#0958d9", "#52c41a", "#faad14", "#f5222d"][i % 4] }}
              />
            ))}
          </div>
        )}
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div>
            <h2 style={{ margin: 0 }}>🎯 Lộ trình học tập cá nhân</h2>
            <div style={{ marginTop: 6, color: "#333" }}>
              Dựa trên bài kiểm tra đầu vào {formatVNDate(myPath?.assessment_date || plan?.created_at)}
            </div>
            <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <strong>Trình độ:</strong>
              <StudentLevelBadge level={levelDisplay.label} />
              <span style={{ color: "#666" }}>({String(levelDisplay.label || "").toUpperCase()})</span>
            </div>
            <div style={{ marginTop: 10, color: "#555" }}>
              Tiến độ: {progress.completed_tasks}/{progress.total_tasks} nhiệm vụ ({progress.percent}%)
            </div>
            <div style={{ marginTop: 6, width: "100%", maxWidth: 520, height: 10, borderRadius: 999, background: "#f0f0f0", overflow: "hidden" }}>
              <div style={{ width: `${Math.max(0, Math.min(100, Number(progress.percent) || 0))}%`, height: "100%", background: "#1677ff" }} />
            </div>
            <div style={{ marginTop: 10, color: "#555" }}>
              Lộ trình AI tạo cho trình độ <strong>{String(activeLevel?.label || "Khá").toUpperCase()}</strong>: {planStats.materials} tài liệu | {planStats.exercises} bài tập | {planStats.tests} bài kiểm tra
            </div>
            <div style={{ marginTop: 8, color: "#555" }}>Đã hoàn thành {completedCount}/{timelineTasks.length || 0} nhiệm vụ</div>
          </div>

          <div style={{ display: "flex", gap: 8, alignItems: "flex-start", flexWrap: "wrap" }}>
            <button onClick={generateAndSavePlan} disabled={loading}>Tạo mới & lưu plan</button>
            <button onClick={() => setShowOnlyMine((v) => !v)} style={{ background: "#1D4ED8", color: "#fff", border: "none", padding: "6px 14px", borderRadius: 8, cursor: "pointer" }}>
              {showOnlyMine ? "Xem tất cả" : "⭐ Chỉ xem bài của tôi"}
            </button>
            <button onClick={() => loadPersisted()} disabled={loading}>Tải lại</button>
          </div>
        </div>
      </div>

      {!!assignedTasks.length && (
        <div style={{ ...card, marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <h3 style={{ margin: 0 }}>📌 Nhiệm vụ được giao</h3>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ fontSize: 13, color: "#555" }}>Độ khó luyện tập:</span>
              {PRACTICE_LEVELS.map((lv) => (
                <button key={`assign-${lv.key}`} type="button" onClick={() => setPracticeDifficulty(lv.key)} style={{ border: "1px solid #dbeafe", borderRadius: 999, background: practiceDifficulty === lv.key ? "#1d4ed8" : "#eff6ff", color: practiceDifficulty === lv.key ? "#fff" : "#1e3a8a", padding: "4px 10px", fontSize: 13 }}>
                  {lv.label}
                </button>
              ))}
            </div>
          </div>
          <div style={{ display: "grid", gap: 8 }}>
            {assignedTasks.map((task, idx) => {
              const isWeak = weakTopics.has(String(task?.topic_title || "").toLowerCase());
              const p = topicProgress[String(task?.topic_title || "").toLowerCase()] || null;
              const pct = Math.max(0, Math.min(100, Number(p?.percent) || 0));
              return (
                <div key={`${task?.topic_id || "t"}-${idx}`} style={{ border: "1px solid #eee", borderRadius: 10, padding: 10, display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                  <div>
                    <div style={{ fontWeight: 700 }}>{task?.topic_title || "Chủ đề"}</div>
                    <div style={{ marginTop: 4 }}>
                      <span style={{ fontSize: 12, padding: "2px 8px", borderRadius: 999, background: isWeak ? "#fff1f0" : "#f6ffed", color: isWeak ? "#cf1322" : "#389e0d" }}>
                        Priority: {isWeak ? "high" : "normal"}
                      </span>
                    </div>
                    <div style={{ marginTop: 8, fontSize: 12, color: "#555" }}>Tiến độ chủ đề: {p ? `${p.completed_tasks}/${p.total_tasks} (${pct}%)` : "0%"}</div>
                    <div style={{ marginTop: 4, width: 220, height: 8, borderRadius: 999, background: "#f0f0f0", overflow: "hidden" }}>
                      <div style={{ width: `${pct}%`, height: "100%", background: pct >= 80 ? "#52c41a" : "#1677ff" }} />
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button onClick={() => nav(`/topics/${task?.topic_id || ""}`)} disabled={!task?.topic_id}>Học ngay</button>
                    <button onClick={() => nav(`/practice/${task?.topic_id || ""}?level=${practiceDifficulty}`)} disabled={!task?.topic_id}>Luyện tập</button>
                    <button onClick={() => nav(`/assessments/${task?.quiz_id || ""}`)} disabled={!task?.quiz_id}>Làm quiz</button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {currentPlan && (
        <div style={{ ...card, marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
            <div>
              <h3 style={{ margin: 0 }}>🧠 Adaptive learning plan</h3>
              <div style={{ marginTop: 6, color: "#555" }}>{currentPlan.ai_explanation}</div>
              <div style={{ marginTop: 8, fontSize: 13, color: "#666" }}>
                Dự kiến hoàn thành: {currentPlan.estimated_completion_days} ngày
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={() => setPlanView("sections")} style={{ background: planView === "sections" ? "#1d4ed8" : "#fff", color: planView === "sections" ? "#fff" : "#1d4ed8", border: "1px solid #bfdbfe" }}>Theo loại</button>
              <button onClick={() => setPlanView("timeline")} style={{ background: planView === "timeline" ? "#1d4ed8" : "#fff", color: planView === "timeline" ? "#fff" : "#1d4ed8", border: "1px solid #bfdbfe" }}>Theo ngày</button>
            </div>
          </div>

          {!!currentPlan?.weak_topics?.length && <div style={{ marginTop: 8, color: "#cf1322" }}>Cần ưu tiên: {currentPlan.weak_topics.join(", ")}</div>}
          {!!currentPlan?.strong_topics?.length && <div style={{ marginTop: 6, color: "#389e0d" }}>Thế mạnh: {currentPlan.strong_topics.join(", ")}</div>}

          {planView === "sections" ? (
            <div style={{ marginTop: 12, display: "grid", gap: 10 }}>
              {[
                { key: "study_material", title: "📚 Tài liệu học" },
                { key: "homework", title: "✏️ Bài tập" },
                { key: "quiz", title: "📝 Mini Quiz" },
              ].map((sec) => (
                <div key={sec.key} style={{ border: "1px solid #eee", borderRadius: 10, padding: 10 }}>
                  <div style={{ fontWeight: 700, marginBottom: 8 }}>{sec.title}</div>
                  {(groupedAdaptive[sec.key] || []).map((it) => {
                    const diff = difficultyBadgeStyle(it?.difficulty);
                    const status = it?.status === "hoan_thanh" ? "Hoàn thành ✅" : it?.status === "dang_lam" ? "Đang làm" : "Chưa làm";
                    const action = it?.status === "hoan_thanh" ? "Xem lại" : it?.status === "dang_lam" ? "Tiếp tục" : "Bắt đầu";
                    return (
                      <div key={`${sec.key}-${it.order}-${it.topic_id}`} style={{ display: "flex", justifyContent: "space-between", gap: 10, borderTop: "1px dashed #eee", padding: "8px 0" }}>
                        <div>
                          <div style={{ fontWeight: 600 }}>{itemTypeIcon(it?.type)} {it?.topic_title}</div>
                          <div style={{ marginTop: 4, fontSize: 13, color: "#666" }}>Trạng thái: {status} • ⏱ {it?.estimated_minutes || 15} phút</div>
                          <div style={{ marginTop: 4, fontSize: 13 }} title={it?.reason || ""}>❓ Tại sao? {it?.reason}</div>
                        </div>
                        <div style={{ textAlign: "right" }}>
                          <span style={{ fontSize: 12, padding: "3px 8px", borderRadius: 999, background: diff.bg, color: diff.color }}>{it?.difficulty || "medium"}</span>
                          <div style={{ marginTop: 8 }}><button>{action}</button></div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          ) : (
            <div style={{ marginTop: 12, display: "grid", gap: 8 }}>
              {adaptiveByDay.map(([day, dayItems]) => (
                <div key={day} style={{ border: "1px solid #eee", borderRadius: 10, padding: 10 }}>
                  <div style={{ fontWeight: 700, marginBottom: 6 }}>Day {day}</div>
                  {(dayItems || []).map((it) => (
                    <div key={`day-${day}-${it.order}`} style={{ fontSize: 14, color: "#444", marginBottom: 4 }}>
                      {itemTypeIcon(it?.type)} {it?.topic_title} · {it?.difficulty}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {finalExam && (
        <div style={{ ...card, marginBottom: 12, borderColor: "#91caff", background: "#e6f4ff" }}>
          📝 Bài kiểm tra cuối kỳ: <strong>{formatVNDate(finalExam?.scheduled_at || finalExam?.exam_date || finalExam?.start_at)}</strong> — Bạn đã hoàn thành {completedCount}/{timelineTasks.length || 0} nhiệm vụ.
          {(new Date(finalExam?.scheduled_at || finalExam?.exam_date || finalExam?.start_at).getTime() - Date.now()) / (1000 * 60 * 60 * 24) <= 10 && (
            <button onClick={() => nav("/quiz")} style={{ marginLeft: 10 }}>Bắt đầu ôn thi</button>
          )}
        </div>
      )}

      {showGenerated && <div style={{ marginBottom: 12, padding: 10, border: "1px solid #b7eb8f", background: "#f6ffed", borderRadius: 10 }}>✅ Đã tạo và lưu plan mới.</div>}
      {error && <div style={{ marginBottom: 12, padding: 10, border: "1px solid #ffa39e", background: "#fff1f0", borderRadius: 10 }}>{error}</div>}
      {loading && <div style={{ color: "#666", marginBottom: 12 }}>Đang tải…</div>}

      {!planDays?.length ? (
        <div style={{ ...card, color: "#666" }}>Chưa có learning plan. Bấm <strong>Tạo mới & lưu plan</strong> để tạo lộ trình theo tài liệu.</div>
      ) : (
        <>
          <div style={{ ...card, marginBottom: 12 }}>
            <h3 style={{ marginTop: 0 }}>📍 Timeline nhiệm vụ</h3>
            <div style={{ position: "relative", paddingLeft: 18 }}>
              <div style={{ position: "absolute", left: 6, top: 0, bottom: 0, width: 2, background: "#e5e7eb" }} />
              {timelineTasks
                .filter(({ task }) => !showOnlyMine || assignedTopicIds.has(Number(task?.topic_id)))
                .map(({ dayIndex, taskIndex, dayTitle, task }) => {
                  const key = `${dayIndex}-${taskIndex}`;
                  const done = !!taskCompletion?.[key];
                  const inProgress = !done && dayIndex === Number(selectedDay);
                  const statusIcon = done ? "✅" : inProgress ? "📖" : "⏳";
                  const statusText = done ? "Hoàn thành" : inProgress ? "Đang học" : "Chưa bắt đầu";
                  return (
                    <div key={key} className={`timeline-item ${done ? "done" : ""}`} style={{ marginBottom: 12, padding: 12, border: "1px solid #eee", borderRadius: 12, marginLeft: 12 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                        <div>
                          <div style={{ fontSize: 13, color: "#666" }}>Bài {dayIndex} • {dayTitle}</div>
                          <div style={{ fontWeight: 700, marginTop: 2 }}>{statusIcon} {task?.title || "(Không có tiêu đề)"}</div>
                          <div style={{ marginTop: 4, color: "#555" }}>{task?.instructions || "Nhiệm vụ học tập trong lộ trình cá nhân của bạn."}</div>
                          <div style={{ marginTop: 6, fontSize: 13, color: "#666" }}>Trạng thái: {statusText} • ⏱ ~{task?.estimated_minutes || 15} phút</div>
                        </div>
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "flex-start" }}>
                          <button onClick={() => nav(`/topics/${task?.topic_id || ""}`)} disabled={!task?.topic_id}>Học ngay</button>
                          <button onClick={() => nav(`/practice/${task?.topic_id || ""}`)} disabled={!task?.topic_id}>Làm quiz</button>
                          <button onClick={() => { setSelectedDay(dayIndex); toggleTask(dayIndex, taskIndex, true); }}>✅ Đánh dấu hoàn thành</button>
                        </div>
                      </div>
                      {!!task?.topic_id && <TopicPracticePreview topicId={Number(task.topic_id)} userId={Number(userId)} nav={nav} />}
                    </div>
                  );
                })}
            </div>
          </div>

          {currentDay && (
            <div style={card}>
              <h3 style={{ marginTop: 0 }}>{currentDay.title}</h3>
              <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 12, padding: 14, marginBottom: 14 }}>
                <MarkdownLite text={currentDay.lesson_md || "(Chưa có nội dung bài học)"} />
              </div>

              <div style={{ marginTop: 12, paddingTop: 16, borderTop: "1px dashed #eee" }}>
                <h4 style={{ margin: "0 0 10px 0" }}>🏠 Bài tập tự luận</h4>
                {!currentDay.homework ? (
                  <div style={{ color: "#666" }}>Hôm nay chưa có bài tập.</div>
                ) : (
                  <>
                    {!!(currentDay.homework?.mcq_questions || []).length && (
                      <div style={{ marginBottom: 14 }}>
                        <div style={{ fontWeight: 700, marginBottom: 8 }}>Phần A — Trắc nghiệm</div>
                        {(currentDay.homework.mcq_questions || []).map((q, qi) => {
                          const qid = q.question_id || `mcq_${qi + 1}`;
                          const chosen = homeworkDrafts?.[currentDay.day_index]?.mcq?.[qid];
                          return (
                            <div key={qid} style={{ border: "1px solid #eee", borderRadius: 12, padding: 12, marginBottom: 10, background: "#fff" }}>
                              <div style={{ fontWeight: 700 }}>Câu {qi + 1}</div>
                              <div style={{ marginTop: 6 }}>{q.stem}</div>
                              <div style={{ marginTop: 10, display: "grid", gap: 6 }}>
                                {(q.options || []).map((opt, oi) => (
                                  <label key={oi} style={{ display: "flex", gap: 8 }}>
                                    <input type="radio" name={`d${currentDay.day_index}-${qid}`} checked={Number(chosen) === Number(oi)} onChange={() => setMcqDraft(currentDay.day_index, qid, oi)} disabled={!!homeworkGrades?.[currentDay.day_index]} />
                                    <span>{String.fromCharCode(65 + oi)}. {opt}</span>
                                  </label>
                                ))}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    <div style={{ marginBottom: 10 }}>
                      <div style={{ fontWeight: 700, marginBottom: 8 }}>Phần B — Tự luận</div>
                      <div style={{ color: "#333" }}>{currentDay.homework.stem}</div>
                      <textarea
                        value={homeworkDrafts?.[currentDay.day_index]?.essay || ""}
                        onChange={(e) => setEssayDraft(currentDay.day_index, e.target.value)}
                        rows={7}
                        placeholder="Viết câu trả lời của bạn ở đây…"
                        style={{ width: "100%", marginTop: 10, padding: 10, borderRadius: 10, border: "1px solid #ddd" }}
                        disabled={!!homeworkGrades?.[currentDay.day_index]}
                      />
                      <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                        <button onClick={() => gradeHomework(currentDay.day_index)} disabled={loading}>Nộp bài</button>
                        {!!homeworkGrades?.[currentDay.day_index] && <button onClick={() => setHomeworkGrades((g) => ({ ...g, [currentDay.day_index]: null }))} style={{ background: "#fff", border: "1px solid #ddd" }}>Làm lại (xoá kết quả)</button>}
                      </div>
                    </div>

                    {!!homeworkGrades?.[currentDay.day_index] && (
                      <div style={{ marginTop: 12, padding: 12, border: "1px solid #eee", borderRadius: 12, background: "#fafafa" }}>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                          <div style={{ fontWeight: 800 }}>📌 Kết quả chấm</div>
                          <ScorePill score={Number(homeworkGrades[currentDay.day_index]?.score_points || 0)} max={Number(homeworkGrades[currentDay.day_index]?.max_points || 0)} />
                        </div>
                        {homeworkGrades[currentDay.day_index]?.comment && <div style={{ marginTop: 10, whiteSpace: "pre-wrap" }}><strong>Nhận xét:</strong> {homeworkGrades[currentDay.day_index]?.comment}</div>}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
