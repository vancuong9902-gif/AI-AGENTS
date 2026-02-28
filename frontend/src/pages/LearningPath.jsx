import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";

function MarkdownLite({ text }) {
  const blocks = useMemo(() => {
    const src = String(text || "").replace(/\r\n/g, "\n");
    if (!src.trim()) return [];
    const lines = src.split("\n");

    const out = [];
    let i = 0;

    const isUl = (l) => /^-\s+/.test(l);
    const isOl = (l) => /^\d+[\.|\)]\s+/.test(l);
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
          items.push(String(lines[i]).replace(/^\d+[\.|\)]\s+/, "").trim());
          i += 1;
        }
        out.push({ type: "ol", items });
        continue;
      }

      // paragraph block
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

function TaskRow({ task, checked, onToggle, assigned }) {
  const t = task || {};
  const title = t.title || "(Không có tiêu đề)";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 10,
        padding: "10px 12px",
        border: "1px solid #eee",
        borderRadius: 10,
        marginBottom: 8,
        background: checked ? "#f6fffb" : "#fff",
      }}
    >
      <input type="checkbox" checked={!!checked} onChange={(e) => onToggle(!!e.target.checked)} style={{ marginTop: 4 }} />
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 700 }}>
          {title}
          {assigned && (
            <span
              style={{
                background: "#1D4ED8",
                color: "#fff",
                fontSize: 11,
                padding: "2px 9px",
                borderRadius: 12,
                marginLeft: 8,
              }}
            >
              ⭐ Phù hợp với bạn
            </span>
          )}
        </div>
        {t.instructions && <div style={{ color: "#555", marginTop: 4 }}>{t.instructions}</div>}
        {t.type === "quiz" && (
          <div style={{ marginTop: 6, color: "#666" }}>
            ✅ Quiz đã được tích hợp vào <strong>Bài tập về nhà</strong>.
          </div>
        )}
      </div>
      <div style={{ color: "#777", fontSize: 12, minWidth: 86, textAlign: "right" }}>{t.estimated_minutes ? `${t.estimated_minutes} phút` : ""}</div>
    </div>
  );
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

  // { "day-task": true/false }
  const [taskCompletion, setTaskCompletion] = useState({});

  // drafts[day] = { essay: string, mcq: { [questionId]: chosenIndex } }
  const [homeworkDrafts, setHomeworkDrafts] = useState({});
  const [homeworkGrades, setHomeworkGrades] = useState({});

  const [showGenerated, setShowGenerated] = useState(false);
  const [myPath, setMyPath] = useState(null);
  const [showOnlyMine, setShowOnlyMine] = useState(false);

  const currentDay = useMemo(() => {
    return (planDays || []).find((d) => Number(d.day_index) === Number(selectedDay)) || null;
  }, [planDays, selectedDay]);

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
        const essay = obj?.answer_text || "";
        const mcq = obj?.answer_json?.mcq_answers || {};
        drafts[di] = { essay, mcq };
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
      // Save for the current student.
      await apiJson(`/profile/${userId}/learning-path?save_plan=1&with_plan=1`);
      setShowGenerated(true);
      await loadPersisted();
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
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  useEffect(() => {
    apiJson(`/lms/student/${userId}/my-path`)
      .then((d) => setMyPath(d?.data || null))
      .catch(() => {});
  }, [userId]);

  async function toggleTask(dayIndex, taskIndex, completed) {
    const key = `${dayIndex}-${taskIndex}`;
    setTaskCompletion((m) => ({ ...m, [key]: !!completed }));

    if (!planId) return; // not persisted
    try {
      await apiJson(`/learning-plans/${planId}/tasks/complete`, {
        method: "POST",
        body: JSON.stringify({ user_id: userId, day_index: dayIndex, task_index: taskIndex, completed: !!completed }),
      });
    } catch (e) {
      // keep optimistic UI; show error only
      setError(String(e?.message || e));
    }
  }

  function setEssayDraft(dayIndex, value) {
    setHomeworkDrafts((prev) => {
      const day = { ...(prev[dayIndex] || { essay: "", mcq: {} }) };
      day.essay = value;
      return { ...prev, [dayIndex]: day };
    });
  }

  function setMcqDraft(dayIndex, questionId, chosenIndex) {
    setHomeworkDrafts((prev) => {
      const day = { ...(prev[dayIndex] || { essay: "", mcq: {} }) };
      const mcq = { ...(day.mcq || {}) };
      mcq[String(questionId)] = Number(chosenIndex);
      day.mcq = mcq;
      return { ...prev, [dayIndex]: day };
    });
  }

  async function gradeHomework(dayIndex) {
    if (!planId) {
      setError("Cần lưu plan trước khi nộp bài (bấm: 'Tạo mới & lưu plan').");
      return;
    }

    const draft = homeworkDrafts?.[dayIndex] || { essay: "", mcq: {} };
    const essay = String(draft.essay || "");
    const mcqAnswers = draft.mcq || {};

    const hasMcq = Object.keys(mcqAnswers || {}).length > 0;
    const hasEssay = essay.trim().length > 0;
    if (!hasMcq && !hasEssay) {
      setError("Bạn chưa làm bài. Hãy chọn đáp án trắc nghiệm hoặc viết phần tự luận rồi nộp.");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const payload = {
        user_id: userId,
        day_index: dayIndex,
        answer_text: essay,
        mcq_answers: mcqAnswers,
      };
      const data = await apiJson(`/learning-plans/${planId}/homework/grade`, {
        method: "POST",
        body: JSON.stringify(payload),
      });

      setHomeworkGrades((g) => ({ ...g, [dayIndex]: data || null }));

      // Auto-mark the "homework" task as done (if present)
      const dayObj = (planDays || []).find((d) => Number(d.day_index) === Number(dayIndex));
      const hwTaskIndex = (dayObj?.tasks || []).findIndex((t) => (t?.type || "").toLowerCase() === "homework");
      if (hwTaskIndex >= 0) {
        await toggleTask(dayIndex, hwTaskIndex, true);
      }
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }


  const assignedTopicIds = new Set((myPath?.assigned_tasks || []).map((t) => Number(t?.topic_id)).filter((v) => Number.isFinite(v)));
  const isAssigned = (task) => assignedTopicIds.has(Number(task?.topic_id));

  const filteredTaskEntries = (currentDay?.tasks || [])
    .map((task, idx) => ({ task, idx }))
    .filter(({ task }) => !showOnlyMine || isAssigned(task));

  const pageWrap = { maxWidth: 980, margin: "0 auto", padding: 16 };
  const card = { border: "1px solid #eee", borderRadius: 14, padding: 16, background: "#fff" };

  return (
    <div style={pageWrap}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 12 }}>
        <div>
          <h2 style={{ margin: 0 }}>📌 Learning Path (mỗi ngày 1 bài + 1 bài tập)</h2>
          <div style={{ color: "#666", marginTop: 4 }}>
            Học sinh đọc <strong>1 bài như sách giáo khoa</strong> mỗi ngày, rồi làm <strong>Bài tập về nhà</strong> (trắc nghiệm + tự luận) để nhận điểm.
            {myPath?.student_level && <span> • Level hiện tại: <strong>{myPath.student_level}</strong></span>}
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "flex-end" }}>
          <button onClick={generateAndSavePlan} disabled={loading}>
            Tạo mới & lưu plan
          </button>
          <button
            onClick={() => setShowOnlyMine((v) => !v)}
            disabled={loading}
            style={{ background: "#1D4ED8", color: "#fff", border: "none", padding: "6px 14px", borderRadius: 8, cursor: "pointer" }}
          >
            {showOnlyMine ? "Xem tất cả" : "⭐ Chỉ xem bài của tôi"}
          </button>
          <button onClick={() => loadPersisted()} disabled={loading}>
            Tải lại
          </button>
        </div>
      </div>

      {showGenerated && (
        <div style={{ marginBottom: 12, padding: 10, border: "1px solid #b7eb8f", background: "#f6ffed", borderRadius: 10 }}>
          ✅ Đã tạo và lưu plan mới.
        </div>
      )}

      {error && (
        <div style={{ marginBottom: 12, padding: 10, border: "1px solid #ffa39e", background: "#fff1f0", borderRadius: 10 }}>
          {error}
        </div>
      )}

      {loading && <div style={{ color: "#666", marginBottom: 12 }}>Đang tải…</div>}

      {!planDays?.length ? (
        <div style={{ ...card, color: "#666" }}>
          Chưa có learning plan. Bấm <strong>Tạo mới & lưu plan</strong> để tạo lộ trình theo tài liệu.
        </div>
      ) : (
        <>
          <div style={{ ...card, marginBottom: 12 }}>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {(planDays || []).map((d) => (
                <button
                  key={d.day_index}
                  onClick={() => setSelectedDay(d.day_index)}
                  style={{
                    padding: "8px 10px",
                    borderRadius: 999,
                    border: selectedDay === d.day_index ? "1px solid #1677ff" : "1px solid #ddd",
                    background: selectedDay === d.day_index ? "#e6f4ff" : "#fff",
                    cursor: "pointer",
                  }}
                >
                  Bài {d.day_index}
                </button>
              ))}
            </div>
            {plan?.summary && (
              <div style={{ marginTop: 12, color: "#555", whiteSpace: "pre-wrap" }}>
                <strong>Tóm tắt lộ trình:</strong> {plan.summary}
              </div>
            )}
          </div>

          {currentDay && (
            <div style={card}>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                <div>
                  <h3 style={{ marginTop: 0, marginBottom: 6 }}>{currentDay.title}</h3>
                  {!!(currentDay.objectives || []).length && (
                    <ul style={{ margin: "0 0 0 20px", color: "#555" }}>
                      {(currentDay.objectives || []).map((o, idx) => (
                        <li key={idx}>{o}</li>
                      ))}
                    </ul>
                  )}
                </div>

                {/* Score summary */}
                {homeworkGrades?.[currentDay.day_index] && (
                  <div style={{ marginTop: 2 }}>
                    <ScorePill
                      score={Number(homeworkGrades[currentDay.day_index]?.score_points || 0)}
                      max={Number(homeworkGrades[currentDay.day_index]?.max_points || 0)}
                    />
                  </div>
                )}
              </div>

              {/* Lesson */}
              <div style={{ marginTop: 14, padding: 14, border: "1px solid #f0f0f0", borderRadius: 12, background: "#fcfcff" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 8 }}>
                  <h4 style={{ margin: 0 }}>📘 Bài học hôm nay</h4>
                  <button
                    onClick={() => {
                      const taskIndex = (currentDay.tasks || []).findIndex((t) => (t?.type || "").toLowerCase() === "read");
                      if (taskIndex >= 0) toggleTask(currentDay.day_index, taskIndex, true);
                    }}
                    style={{ fontSize: 13 }}
                  >
                    ✅ Đánh dấu đã đọc
                  </button>
                </div>
                <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 12, padding: 14 }}>
                  <MarkdownLite text={currentDay.lesson_md || "(Chưa có nội dung bài học)"} />
                </div>
              </div>

              {/* Tasks */}
              <div style={{ marginTop: 14 }}>
                <h4 style={{ margin: "0 0 10px 0" }}>📋 Nhiệm vụ hôm nay</h4>
                {filteredTaskEntries.length ? (
                  filteredTaskEntries.map(({ task: t, idx }) => {
                    const key = `${currentDay.day_index}-${idx}`;
                    return (
                      <TaskRow
                        key={key}
                        task={t}
                        checked={!!taskCompletion?.[key]}
                        onToggle={(val) => toggleTask(currentDay.day_index, idx, val)}
                        assigned={isAssigned(t)}
                      />
                    );
                  })
                ) : (
                  <div style={{ color: "#666" }}>Không có nhiệm vụ.</div>
                )}
              </div>

              {/* Homework */}
              <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px dashed #eee" }}>
                <h4 style={{ margin: "0 0 10px 0" }}>🏠 Bài tập về nhà</h4>

                {!currentDay.homework ? (
                  <div style={{ color: "#666" }}>Hôm nay chưa có bài tập.</div>
                ) : (
                  <>
                    {/* MCQ */}
                    {!!(currentDay.homework?.mcq_questions || []).length && (
                      <div style={{ marginBottom: 14 }}>
                        <div style={{ fontWeight: 700, marginBottom: 8 }}>Phần A — Trắc nghiệm</div>
                        {(currentDay.homework.mcq_questions || []).map((q, qi) => {
                          const qid = q.question_id || `mcq_${qi + 1}`;
                          const chosen = homeworkDrafts?.[currentDay.day_index]?.mcq?.[qid];

                          // If graded, find breakdown for this q
                          const g = homeworkGrades?.[currentDay.day_index];
                          const gb = (g?.mcq_breakdown || []).find((x) => String(x?.question_id) === String(qid));
                          const correctIndex = gb?.correct_index;

                          return (
                            <div
                              key={qid}
                              style={{
                                border: "1px solid #eee",
                                borderRadius: 12,
                                padding: 12,
                                marginBottom: 10,
                                background: "#fff",
                              }}
                            >
                              <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                                <div style={{ fontWeight: 700 }}>
                                  Câu {qi + 1} ({q.max_points || 1}đ)
                                </div>
                                {gb && (
                                  <div style={{ color: gb.is_correct ? "#1f7a1f" : "#a8071a", fontWeight: 700 }}>
                                    {gb.score_points}/{gb.max_points}đ
                                  </div>
                                )}
                              </div>
                              <div style={{ marginTop: 6 }}>{q.stem}</div>

                              <div style={{ marginTop: 10, display: "grid", gap: 6 }}>
                                {(q.options || []).map((opt, oi) => {
                                  const isChosen = Number(chosen) === Number(oi);
                                  const isCorrect = Number(correctIndex) === Number(oi);

                                  return (
                                    <label
                                      key={oi}
                                      style={{
                                        display: "flex",
                                        alignItems: "flex-start",
                                        gap: 8,
                                        padding: "8px 10px",
                                        borderRadius: 10,
                                        border: "1px solid #eee",
                                        background: gb
                                          ? isCorrect
                                            ? "#f6ffed"
                                            : isChosen
                                              ? "#fff1f0"
                                              : "#fff"
                                          : isChosen
                                            ? "#f0f7ff"
                                            : "#fff",
                                      }}
                                    >
                                      <input
                                        type="radio"
                                        name={`d${currentDay.day_index}-${qid}`}
                                        checked={isChosen}
                                        onChange={() => setMcqDraft(currentDay.day_index, qid, oi)}
                                        disabled={!!gb}
                                        style={{ marginTop: 3 }}
                                      />
                                      <span>
                                        {String.fromCharCode(65 + oi)}. {opt}
                                        {gb && isCorrect && <span style={{ marginLeft: 8, color: "#1f7a1f", fontWeight: 700 }}>✓ Đúng</span>}
                                        {gb && isChosen && !isCorrect && <span style={{ marginLeft: 8, color: "#a8071a", fontWeight: 700 }}>✗ Bạn chọn</span>}
                                      </span>
                                    </label>
                                  );
                                })}
                              </div>

                              {/* Instant detailed answer after student chooses (practice-friendly) */}
                              {!gb && chosen != null && chosen !== "" && Number.isFinite(Number(q.correct_index)) && (
                                (() => {
                                  const chosenI = Number(chosen);
                                  const correctI = Number(q.correct_index);
                                  const isCorrectNow = chosenI === correctI;
                                  const chosenText = (q.options || [])[chosenI] || "";
                                  const correctText = (q.options || [])[correctI] || "";
                                  return (
                                    <div
                                      style={{
                                        marginTop: 10,
                                        background: isCorrectNow ? "#f6ffed" : "#fff1f0",
                                        border: isCorrectNow ? "1px solid #b7eb8f" : "1px solid #ffccc7",
                                        borderRadius: 12,
                                        padding: 10,
                                        color: "#333",
                                      }}
                                    >
                                      <div style={{ fontWeight: 900 }}>{isCorrectNow ? "✅ Đúng" : "❌ Sai"}</div>
                                      {!isCorrectNow && (
                                        <div style={{ marginTop: 6 }}>
                                          Bạn chọn: <b>{chosenText || `(${chosenI})`}</b>
                                        </div>
                                      )}
                                      <div style={{ marginTop: 6 }}>
                                        Đáp án đúng: <b>{correctText || `(${correctI})`}</b>
                                      </div>
                                      {q.explanation ? (
                                        <div style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>
                                          <b>Giải thích:</b> {q.explanation}
                                        </div>
                                      ) : null}
                                    </div>
                                  );
                                })()
                              )}

                              {gb?.explanation && (
                                <div style={{ marginTop: 10, color: "#555" }}>
                                  <strong>Giải thích:</strong> {gb.explanation}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {/* Essay */}
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
                        <button onClick={() => gradeHomework(currentDay.day_index)} disabled={loading}>
                          Nộp bài & chấm điểm
                        </button>
                        {!!homeworkGrades?.[currentDay.day_index] && (
                          <button
                            onClick={() => {
                              // allow re-submit by clearing grade
                              setHomeworkGrades((g) => ({ ...g, [currentDay.day_index]: null }));
                            }}
                            style={{ background: "#fff", border: "1px solid #ddd" }}
                          >
                            Làm lại (xoá kết quả)
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Grading details */}
                    {!!homeworkGrades?.[currentDay.day_index] && (
                      <div style={{ marginTop: 12, padding: 12, border: "1px solid #eee", borderRadius: 12, background: "#fafafa" }}>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                          <div style={{ fontWeight: 800 }}>📌 Kết quả chấm</div>
                          <ScorePill
                            score={Number(homeworkGrades[currentDay.day_index]?.score_points || 0)}
                            max={Number(homeworkGrades[currentDay.day_index]?.max_points || 0)}
                          />
                        </div>

                        {homeworkGrades[currentDay.day_index]?.comment && (
                          <div style={{ marginTop: 10, whiteSpace: "pre-wrap" }}>
                            <strong>Nhận xét:</strong> {homeworkGrades[currentDay.day_index]?.comment}
                          </div>
                        )}

                        {!!(homeworkGrades[currentDay.day_index]?.rubric_breakdown || []).length && (
                          <div style={{ marginTop: 12 }}>
                            <div style={{ fontWeight: 700, marginBottom: 6 }}>Rubric (tự luận)</div>
                            <div style={{ display: "grid", gap: 8 }}>
                              {(homeworkGrades[currentDay.day_index]?.rubric_breakdown || []).map((r, idx) => (
                                <div key={idx} style={{ padding: 10, borderRadius: 10, border: "1px solid #e6e6e6", background: "#fff" }}>
                                  <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                                    <strong>{r.criterion}</strong>
                                    <span style={{ fontWeight: 700 }}>
                                      {r.score}/{r.max}
                                    </span>
                                  </div>
                                  {r.feedback && <div style={{ color: "#555", marginTop: 6 }}>{r.feedback}</div>}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        <div style={{ marginTop: 12, color: "#666" }}>
                          Muốn hỏi lại/hiểu sâu hơn? Bạn có thể qua <button onClick={() => nav("/tutor")} style={{ padding: "2px 8px" }}>Tutor</button> và dán câu hỏi kèm đoạn bạn chưa hiểu.
                        </div>
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
