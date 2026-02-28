import { useEffect, useMemo, useRef, useState } from "react";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";

const stepTitle = {
  1: "Bước 1 — Entry Test",
  2: "Bước 2 — Kết quả + Lộ trình",
  3: "Bước 3 — Học bài + Bài tập",
  4: "Bước 4 — Final Exam",
  5: "Bước 5 — Kết quả tổng kết",
};

const levelColor = {
  beginner: "#cf1322",
  intermediate: "#d48806",
  advanced: "#389e0d",
};

function fmt(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  const mm = String(Math.floor(s / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function estimateTimeSec(questions = []) {
  const mins = (questions || []).reduce((acc, q) => acc + Number(q?.estimated_minutes || 0), 0);
  const safe = Number.isFinite(mins) && mins > 0 ? mins : Math.max(10, Math.ceil((questions || []).length * 1.5));
  return Math.round(safe * 60);
}

function examBreakdownBySection(rows = []) {
  const out = {};
  for (const item of rows || []) {
    const section = String(item?.section || "MEDIUM").toUpperCase();
    out[section] = out[section] || { earned: 0, total: 0 };
    out[section].earned += Number(item?.score_points || 0);
    out[section].total += Number(item?.max_points || 0);
  }
  return Object.entries(out).map(([section, s]) => ({
    section,
    percent: s.total > 0 ? Math.round((s.earned / s.total) * 100) : 0,
  }));
}

export default function AgentFlow() {
  const { userId: authUserId } = useAuth();
  const userId = Number(localStorage.getItem("user_id") || authUserId || 1);

  const [currentStep, setCurrentStep] = useState(1);
  const [docs, setDocs] = useState([]);
  const [selectedDocId, setSelectedDocId] = useState("");
  const [topics, setTopics] = useState([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const [entryQuiz, setEntryQuiz] = useState(null);
  const [entryAnswers, setEntryAnswers] = useState({});
  const [entryTimer, setEntryTimer] = useState(null);
  const [entryStartedAt, setEntryStartedAt] = useState(null);
  const entryAutoRef = useRef(false);
  const [entryTestResult, setEntryTestResult] = useState(null);

  const [learningPlan, setLearningPlan] = useState(null);
  const [topicProgress, setTopicProgress] = useState({});
  const [topicExercise, setTopicExercise] = useState(null);
  const [topicAnswers, setTopicAnswers] = useState({});
  const [topicResult, setTopicResult] = useState(null);

  const [finalQuiz, setFinalQuiz] = useState(null);
  const [finalAnswers, setFinalAnswers] = useState({});
  const [finalTimer, setFinalTimer] = useState(null);
  const [finalStartedAt, setFinalStartedAt] = useState(null);
  const finalAutoRef = useRef(false);
  const [finalExamResult, setFinalExamResult] = useState(null);

  const planTopics = useMemo(() => {
    const days = learningPlan?.plan?.days || [];
    const out = [];
    days.forEach((d, idx) => {
      const title = d?.topic || d?.title || `Topic ${idx + 1}`;
      out.push({ id: `${idx + 1}`, title, day: Number(d?.day_index || idx + 1), tasks: d?.tasks || [] });
    });
    return out;
  }, [learningPlan]);

  const completedCount = Object.values(topicProgress || {}).filter((x) => !!x?.completed).length;
  const completionRate = planTopics.length > 0 ? completedCount / planTopics.length : 0;

  useEffect(() => {
    (async () => {
      try {
        const data = await apiJson("/documents");
        const arr = data?.documents || [];
        setDocs(arr);
        if (arr.length > 0) setSelectedDocId(String(arr[0].document_id));
      } catch {
        // ignore
      }
    })();
  }, []);

  useEffect(() => {
    (async () => {
      if (!selectedDocId) return;
      try {
        const data = await apiJson(`/agent/documents/${selectedDocId}/phase1`);
        const t = (data?.topics || []).map((x) => x?.title).filter(Boolean);
        setTopics(t);
      } catch {
        setTopics([]);
      }
    })();
  }, [selectedDocId]);

  useEffect(() => {
    if (entryTimer == null || !entryQuiz || entryTestResult) return;
    const t = setInterval(() => setEntryTimer((p) => Math.max(0, (p || 0) - 1)), 1000);
    return () => clearInterval(t);
  }, [entryTimer, entryQuiz, entryTestResult]);

  useEffect(() => {
    if (entryTimer !== 0 || entryAutoRef.current || entryTestResult || !entryQuiz) return;
    entryAutoRef.current = true;
    submitEntry(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entryTimer, entryTestResult, entryQuiz]);

  useEffect(() => {
    if (finalTimer == null || !finalQuiz || finalExamResult) return;
    const t = setInterval(() => setFinalTimer((p) => Math.max(0, (p || 0) - 1)), 1000);
    return () => clearInterval(t);
  }, [finalTimer, finalQuiz, finalExamResult]);

  useEffect(() => {
    if (finalTimer !== 0 || finalAutoRef.current || finalExamResult || !finalQuiz) return;
    finalAutoRef.current = true;
    submitFinal(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finalTimer, finalExamResult, finalQuiz]);

  async function generateEntry() {
    setStatus("Đang tạo bài kiểm tra đầu vào...");
    setError("");
    try {
      const data = await apiJson("/agent/entry-test/generate", {
        method: "POST",
        body: {
          user_id: userId,
          document_ids: selectedDocId ? [Number(selectedDocId)] : [],
          topics,
          language: "vi",
        },
      });
      setEntryQuiz(data);
      setEntryAnswers({});
      setEntryStartedAt(Date.now());
      setEntryTimer(estimateTimeSec(data?.questions || []));
      setStatus("Đã tạo entry test.");
    } catch (e) {
      setError(e?.message || "Không tạo được entry test");
    }
  }

  async function submitEntry(auto = false) {
    if (!entryQuiz?.quiz_id) return;
    setStatus("Đang nộp bài đầu vào...");
    try {
      const answerList = (entryQuiz?.questions || []).map((q) => ({
        question_id: q.question_id,
        answer_index: entryAnswers[q.question_id]?.answer_index ?? null,
        answer_text: entryAnswers[q.question_id]?.answer_text ?? null,
      }));
      const duration = entryStartedAt ? Math.round((Date.now() - entryStartedAt) / 1000) : 0;
      const data = await apiJson(`/agent/entry-test/${entryQuiz.quiz_id}/submit`, {
        method: "POST",
        body: { user_id: userId, duration_sec: duration, answers: answerList },
      });
      const normalized = {
        score: Number(data?.score_percent || 0),
        level: String(data?.classification || "beginner"),
        breakdown: data?.breakdown || [],
      };
      setEntryTestResult(normalized);
      setCurrentStep(2);
      await loadLearningPlan();
      setStatus(auto ? "Hết giờ: đã tự nộp entry test." : "Đã nộp entry test.");
    } catch (e) {
      setError(e?.message || "Nộp entry test thất bại");
    }
  }

  async function loadLearningPlan() {
    try {
      const data = await apiJson(`/learning-plans/${userId}/latest`);
      setLearningPlan(data || null);
      const init = {};
      (data?.plan?.days || []).forEach((d, idx) => {
        init[String(idx + 1)] = { completed: false, score: null };
      });
      setTopicProgress((prev) => ({ ...init, ...prev }));
    } catch {
      setLearningPlan(null);
    }
  }

  async function generateTopicExercise(topic) {
    setStatus(`Đang tạo bài tập cho topic: ${topic.title}`);
    setTopicResult(null);
    try {
      const data = await apiJson("/agent/topic-exercises/generate", {
        method: "POST",
        body: { user_id: userId, topic_id: Number(topic.id), language: "vi" },
      });
      setTopicExercise({ ...data, topic });
      setTopicAnswers({});
      setCurrentStep(3);
    } catch (e) {
      setError(e?.message || "Không tạo được bài tập topic");
    }
  }

  async function submitTopicExercise() {
    if (!topicExercise?.quiz_id || !topicExercise?.topic) return;
    setStatus("Đang nộp bài tập topic...");
    try {
      const answerList = (topicExercise?.questions || []).map((q) => ({
        question_id: q.question_id,
        answer_index: topicAnswers[q.question_id]?.answer_index ?? null,
        answer_text: topicAnswers[q.question_id]?.answer_text ?? null,
      }));
      const data = await apiJson(`/agent/topic-exercises/${topicExercise.quiz_id}/submit`, {
        method: "POST",
        body: {
          user_id: userId,
          topic_id: Number(topicExercise.topic.id),
          duration_sec: 0,
          answers: answerList,
        },
      });
      setTopicResult(data);
      setTopicProgress((prev) => ({
        ...prev,
        [String(topicExercise.topic.id)]: {
          completed: true,
          score: Number(data?.score_percent || 0),
        },
      }));
    } catch (e) {
      setError(e?.message || "Nộp bài tập topic thất bại");
    }
  }

  async function generateFinal() {
    setStatus("Đang tạo final exam...");
    setError("");
    try {
      const data = await apiJson("/agent/final-exam/generate", {
        method: "POST",
        body: {
          user_id: userId,
          document_ids: selectedDocId ? [Number(selectedDocId)] : [],
          topics,
          language: "vi",
        },
      });
      setFinalQuiz(data);
      setFinalAnswers({});
      setFinalStartedAt(Date.now());
      setFinalTimer(estimateTimeSec(data?.questions || []));
      setCurrentStep(4);
      setStatus("Đã tạo final exam.");
    } catch (e) {
      setError(e?.message || "Không tạo được final exam");
    }
  }

  async function submitFinal(auto = false) {
    if (!finalQuiz?.quiz_id) return;
    setStatus("Đang nộp final exam...");
    try {
      const answerList = (finalQuiz?.questions || []).map((q) => ({
        question_id: q.question_id,
        answer_index: finalAnswers[q.question_id]?.answer_index ?? null,
        answer_text: finalAnswers[q.question_id]?.answer_text ?? null,
      }));
      const duration = finalStartedAt ? Math.round((Date.now() - finalStartedAt) / 1000) : 0;
      const data = await apiJson(`/agent/final-exam/${finalQuiz.quiz_id}/submit`, {
        method: "POST",
        body: { user_id: userId, duration_sec: duration, answers: answerList },
      });
      setFinalExamResult({
        score: Number(data?.score_percent || 0),
        breakdown: examBreakdownBySection(data?.breakdown || []),
        analytics: data?.analytics || {},
      });
      setCurrentStep(5);
      setStatus(auto ? "Hết giờ: đã tự nộp final exam." : "Đã nộp final exam.");
    } catch (e) {
      setError(e?.message || "Nộp final exam thất bại");
    }
  }

  async function sendReport() {
    try {
      await apiJson("/lms/report", {
        method: "POST",
        body: {
          user_id: userId,
          entry_test: entryTestResult,
          final_exam: finalExamResult,
          topic_progress: topicProgress,
        },
      });
      setStatus("Đã gửi báo cáo cho giáo viên.");
    } catch (e) {
      setError(`Không gửi được báo cáo: ${e?.message || "unknown"}`);
    }
  }

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: 16 }}>
      <h2>🧭 Agent Flow (Guided Wizard)</h2>
      <div style={{ color: "#666" }}>User #{userId} • {stepTitle[currentStep]}</div>

      <div style={{ marginTop: 12, background: "#fff", border: "1px solid #eee", borderRadius: 12, padding: 12 }}>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 10 }}>
          <div>
            <div style={{ fontWeight: 700 }}>Tài liệu giảng dạy</div>
            <select value={selectedDocId} onChange={(e) => setSelectedDocId(e.target.value)} style={{ marginTop: 6, width: "100%", padding: 8 }}>
              {(docs || []).map((d) => <option key={d.document_id} value={d.document_id}>{d.title}</option>)}
            </select>
          </div>
          <div>
            <div style={{ fontWeight: 700 }}>Topics</div>
            <div style={{ marginTop: 6, maxHeight: 120, overflow: "auto", border: "1px solid #eee", borderRadius: 8, padding: 8 }}>
              {(topics || []).map((t) => <div key={t}>• {t}</div>)}
            </div>
          </div>
        </div>
      </div>

      {status && <div style={{ marginTop: 12, background: "#f6ffed", border: "1px solid #b7eb8f", padding: 10, borderRadius: 10 }}>{status}</div>}
      {error && <div style={{ marginTop: 12, background: "#fff3f3", border: "1px solid #ffd0d0", padding: 10, borderRadius: 10 }}>{error}</div>}

      <div style={{ marginTop: 14, display: "grid", gap: 12 }}>
        <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 12, padding: 12 }}>
          <h3 style={{ marginTop: 0 }}>1) Entry Test</h3>
          {!entryQuiz && <button onClick={generateEntry}>Bắt đầu bài kiểm tra đầu vào</button>}
          {entryQuiz && !entryTestResult && (
            <>
              <div>⏱️ Còn lại: <b>{fmt(entryTimer)}</b></div>
              {(entryQuiz.questions || []).map((q, i) => (
                <div key={q.question_id} style={{ marginTop: 8, paddingTop: 8, borderTop: "1px dashed #eee" }}>
                  <div><b>Câu {i + 1}</b> ({q.section}/{q.type}): {q.stem}</div>
                  {q.type === "mcq" ? (q.options || []).map((op, idx) => (
                    <label key={idx} style={{ display: "block" }}>
                      <input type="radio" name={`e_${q.question_id}`} checked={entryAnswers[q.question_id]?.answer_index === idx} onChange={() => setEntryAnswers((p) => ({ ...p, [q.question_id]: { answer_index: idx } }))} /> {op}
                    </label>
                  )) : (
                    <textarea rows={2} value={entryAnswers[q.question_id]?.answer_text || ""} onChange={(e) => setEntryAnswers((p) => ({ ...p, [q.question_id]: { answer_text: e.target.value } }))} style={{ width: "100%", marginTop: 6 }} />
                  )}
                </div>
              ))}
              <button onClick={() => submitEntry(false)} style={{ marginTop: 10 }}>Nộp entry test</button>
            </>
          )}
          {entryTestResult && (
            <div>
              Điểm: <b>{entryTestResult.score}%</b> • Level: <b style={{ color: levelColor[entryTestResult.level] }}>{entryTestResult.level}</b>
              <div>Breakdown: {entryTestResult.breakdown.length} câu đã chấm.</div>
            </div>
          )}
        </div>

        <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 12, padding: 12 }}>
          <h3 style={{ marginTop: 0 }}>2) Xem kết quả + lộ trình</h3>
          <button onClick={loadLearningPlan}>Nạp lộ trình học cá nhân</button>
          {learningPlan?.plan && (
            <div style={{ marginTop: 8 }}>
              {(planTopics || []).map((t) => <div key={t.id}>• {t.title}</div>)}
            </div>
          )}
        </div>

        <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 12, padding: 12 }}>
          <h3 style={{ marginTop: 0 }}>3) Học bài + bài tập theo topic</h3>
          {(planTopics || []).map((t) => (
            <div key={t.id} style={{ borderTop: "1px dashed #eee", paddingTop: 8, marginTop: 8 }}>
              <div><b>{t.title}</b> {topicProgress[t.id]?.completed ? "✅" : "⚪"}</div>
              <button onClick={() => generateTopicExercise(t)} style={{ marginTop: 6 }}>Tạo bài tập topic</button>
            </div>
          ))}
          {topicExercise && (
            <div style={{ marginTop: 10 }}>
              <div><b>Bài tập:</b> {topicExercise.topic?.title}</div>
              {(topicExercise.questions || []).map((q) => (
                <div key={q.question_id} style={{ marginTop: 6 }}>
                  <div>{q.stem}</div>
                  {q.type === "mcq" ? (q.options || []).map((op, idx) => (
                    <label key={idx} style={{ display: "block" }}>
                      <input type="radio" name={`t_${q.question_id}`} checked={topicAnswers[q.question_id]?.answer_index === idx} onChange={() => setTopicAnswers((p) => ({ ...p, [q.question_id]: { answer_index: idx } }))} /> {op}
                    </label>
                  )) : <textarea rows={2} value={topicAnswers[q.question_id]?.answer_text || ""} onChange={(e) => setTopicAnswers((p) => ({ ...p, [q.question_id]: { answer_text: e.target.value } }))} style={{ width: "100%" }} />}
                </div>
              ))}
              <button onClick={submitTopicExercise} style={{ marginTop: 8 }}>Nộp bài tập topic</button>
              {topicResult && <div style={{ marginTop: 6 }}>Kết quả: <b>{topicResult.score_percent || 0}%</b></div>}
            </div>
          )}
        </div>

        <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 12, padding: 12 }}>
          <h3 style={{ marginTop: 0 }}>4) Final Exam</h3>
          {completionRate < 0.8 ? <div>Hoàn thành topic: {Math.round(completionRate * 100)}%. Cần ít nhất 80% để mở final exam.</div> : null}
          {completionRate >= 0.8 && !finalQuiz && <button onClick={generateFinal}>Bắt đầu bài kiểm tra cuối kỳ</button>}
          {finalQuiz && !finalExamResult && (
            <>
              <div style={{ color: "#cf1322", fontWeight: 700 }}>⚠️ Đây là bài kiểm tra cuối kỳ, không thể làm lại.</div>
              <div>⏱️ Còn lại: <b>{fmt(finalTimer)}</b></div>
              {(finalQuiz.questions || []).map((q, i) => (
                <div key={q.question_id} style={{ marginTop: 8 }}>
                  <div><b>Câu {i + 1}</b> ({q.section}/{q.type}): {q.stem}</div>
                  {q.type === "mcq" ? (q.options || []).map((op, idx) => (
                    <label key={idx} style={{ display: "block" }}>
                      <input type="radio" name={`f_${q.question_id}`} checked={finalAnswers[q.question_id]?.answer_index === idx} onChange={() => setFinalAnswers((p) => ({ ...p, [q.question_id]: { answer_index: idx } }))} /> {op}
                    </label>
                  )) : <textarea rows={2} value={finalAnswers[q.question_id]?.answer_text || ""} onChange={(e) => setFinalAnswers((p) => ({ ...p, [q.question_id]: { answer_text: e.target.value } }))} style={{ width: "100%" }} />}
                </div>
              ))}
              <button onClick={() => submitFinal(false)} style={{ marginTop: 10 }}>Nộp final exam</button>
            </>
          )}
          {finalExamResult && (
            <div>
              Điểm tổng: <b>{finalExamResult.score}%</b>
              <div style={{ marginTop: 6 }}>
                {(finalExamResult.breakdown || []).map((b) => <div key={b.section}>• {b.section}: {b.percent}%</div>)}
              </div>
            </div>
          )}
        </div>

        <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 12, padding: 12 }}>
          <h3 style={{ marginTop: 0 }}>5) Tổng kết & báo cáo</h3>
          {entryTestResult && finalExamResult && (
            <>
              <div>Entry: {entryTestResult.score}% → Final: {finalExamResult.score}%</div>
              <div style={{ marginTop: 8 }}>
                {(planTopics || []).map((t) => {
                  const done = topicProgress[t.id]?.completed;
                  const sc = Number(topicProgress[t.id]?.score || 0);
                  const mark = done ? (sc >= 80 ? "✅" : sc >= 50 ? "⚠️" : "❌") : "❌";
                  return <div key={t.id}>{mark} {t.title} {done ? `(${sc}%)` : ""}</div>;
                })}
              </div>
              <pre style={{ whiteSpace: "pre-wrap", marginTop: 8, background: "#fafafa", padding: 8, borderRadius: 8 }}>
                {JSON.stringify(finalExamResult.analytics || {}, null, 2)}
              </pre>
            </>
          )}
          <button onClick={sendReport}>Gửi kết quả cho giáo viên</button>
        </div>
      </div>
    </div>
  );
}
