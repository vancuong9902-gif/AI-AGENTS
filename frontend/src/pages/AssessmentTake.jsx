import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";

export default function AssessmentTake() {
  const { id } = useParams();
  const navigate = useNavigate();
  const assessmentId = Number(id);
  const { userId } = useAuth();

  const [data, setData] = useState(null);
  const [answers, setAnswers] = useState({});
  const [startedAt, setStartedAt] = useState(null);
  const [timeLeftSec, setTimeLeftSec] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [pathAssigned, setPathAssigned] = useState(false);

  const autoSubmittedRef = useRef(false);

  const answeredCount = useMemo(() => Object.keys(answers).length, [answers]);

  const qMap = useMemo(() => {
    const m = {};
    for (const q of data?.questions || []) {
      m[q.question_id] = q;
    }
    return m;
  }, [data]);

  const timeLimitSec = useMemo(() => {
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

  const formatDuration = (sec) => {
    const s = Math.max(0, Math.floor(Number(sec || 0)));
    const hh = Math.floor(s / 3600);
    const mm = Math.floor((s % 3600) / 60);
    const ss = s % 60;
    if (hh > 0) return `${hh}h ${String(mm).padStart(2, "0")}m ${String(ss).padStart(2, "0")}s`;
    return `${mm}m ${String(ss).padStart(2, "0")}s`;
  };

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

  const load = async () => {
    setLoading(true);
    setError("");
    setResult(null);
    setPathAssigned(false);
    autoSubmittedRef.current = false;
    try {
      const d = await apiJson(`/assessments/${assessmentId}`, { method: "GET" });
      setData(d);
      setAnswers({});
      setStartedAt(Date.now());
      const mins = Number(d?.time_limit_minutes || 0);
      if (Number.isFinite(mins) && mins > 0) setTimeLeftSec(Math.round(mins * 60));
      else setTimeLeftSec(null);
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

  // Countdown timer
  useEffect(() => {
    if (timeLeftSec == null) return;
    if (result) return;
    if (submitting) return;

    const t = setInterval(() => {
      setTimeLeftSec((prev) => {
        if (prev == null) return prev;
        return Math.max(0, prev - 1);
      });
    }, 1000);

    return () => clearInterval(t);
  }, [timeLeftSec == null, result, submitting]);

  // Auto-submit when time is up
  useEffect(() => {
    if (timeLeftSec !== 0) return;
    if (result) return;
    if (submitting) return;
    if (autoSubmittedRef.current) return;
    autoSubmittedRef.current = true;
    submit(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeLeftSec, result, submitting]);

  const setMcq = (qid, idx) => {
    setAnswers((prev) => ({ ...prev, [qid]: { ...(prev[qid] || {}), answer_index: idx } }));
  };

  const setEssay = (qid, txt) => {
    setAnswers((prev) => ({ ...prev, [qid]: { ...(prev[qid] || {}), answer_text: txt } }));
  };

  const submit = async (auto = false) => {
    if (!data?.assessment_id) return;
    setSubmitting(true);
    setError("");

    try {
      let durationSec = startedAt ? Math.max(0, Math.round((Date.now() - startedAt) / 1000)) : 0;
      if (timeLimitSec > 0 && timeLeftSec != null) {
        const used = Math.max(0, timeLimitSec - timeLeftSec);
        // Prefer timer-based duration (more stable), but keep max.
        durationSec = Math.max(durationSec, used);
      }

      const answerList = (data.questions || []).map((q) => ({
        question_id: q.question_id,
        answer_index: answers[q.question_id]?.answer_index ?? null,
        answer_text: answers[q.question_id]?.answer_text ?? null,
      }));

      const r = await apiJson(`/assessments/${data.assessment_id}/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: Number(userId ?? 1),
          duration_sec: durationSec,
          answers: answerList,
        }),
      });

      setResult(r);

      const isEntryTest = String(r?.assessment_kind || data?.kind || "").toLowerCase() === "diagnostic_pre";
      if (isEntryTest) {
        try {
          await apiJson(`/lms/assign-path`, {
            method: "POST",
            body: {
              user_id: Number(userId ?? 1),
              quiz_id: Number(data?.assessment_id || assessmentId),
              classroom_id: Number(r?.classroom_id || 0),
            },
          });
          setPathAssigned(true);
        } catch (_) {
          setPathAssigned(false);
        }
      }

      if (auto) {
        setError("Hết giờ ⏱️ — hệ thống đã tự nộp bài.");
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
              chunk #{s?.chunk_id ?? "?"}
            </span>
          ))}
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div style={{ maxWidth: 900, margin: "0 auto", padding: 16 }}>
        <h2>Đang tải…</h2>
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

      <div style={{ display: "grid", gap: 14, marginTop: 12 }}>
        {(data?.questions || []).map((q, idx) => (
          <div
            key={q.question_id}
            style={{ background: "#fff", borderRadius: 12, padding: 12, boxShadow: "0 2px 10px rgba(0,0,0,0.06)" }}
          >
            <div style={{ fontWeight: 700, marginBottom: 6 }}>
              Câu {idx + 1} ({q.type === "mcq" ? "Trắc nghiệm" : "Tự luận"})
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
                      disabled={!!result}
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
                  disabled={!!result}
                />
                <div style={{ color: "#666", marginTop: 6 }}>
                  Thang điểm: {q.max_points || 10} (AI sẽ chấm theo rubric)
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      <div style={{ marginTop: 16, display: "flex", gap: 10, alignItems: "center" }}>
        <button onClick={() => submit(false)} disabled={submitting || !!result} style={{ padding: "10px 14px" }}>
          Nộp bài
        </button>
        {submitting && <span style={{ color: "#666" }}>Đang nộp…</span>}
      </div>

      {result && (
        <div style={{ marginTop: 16, display: "grid", gap: 14 }}>
          <div
            style={{
              background: "#f6ffed",
              border: "1px solid #b7eb8f",
              padding: 12,
              borderRadius: 12,
            }}
          >
            <div style={{ fontWeight: 800, fontSize: 16 }}>✅ Nộp bài thành công</div>
            <div
              style={{
                marginTop: 10,
                background: "#fff",
                border: "1px solid #e6f4ff",
                borderRadius: 12,
                padding: 12,
                display: "flex",
                flexWrap: "wrap",
                gap: 12,
              }}
            >
              <span>🏆 Điểm: <b>{result.total_score_percent ?? result.score_percent}/100</b></span>
              <span>📚 Xếp loại: <b>{levelLabel(result.total_score_percent ?? result.score_percent)}</b></span>
              <span>⏱️ Thời gian làm bài: <b>{formatDuration(result.duration_sec ?? 0)}</b></span>
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

            {pathAssigned && (
              <div style={{ marginTop: 10, padding: 10, borderRadius: 10, background: "#fffbe6", border: "1px solid #ffe58f" }}>
                🎯 Dựa trên kết quả, hệ thống đã tạo lộ trình học tập phù hợp cho bạn!
              </div>
            )}

            {result?.synced_diagnostic?.stage === "pre" && (
              <div
                style={{
                  marginTop: 10,
                  background: "#fff",
                  border: "1px solid #e6f4ff",
                  borderRadius: 12,
                  padding: 12,
                }}
              >
                <div style={{ fontWeight: 800 }}>🎯 Placement test đã cập nhật trình độ</div>
                <div style={{ marginTop: 6, color: "#333" }}>
                  Level mới: <b>{result.synced_diagnostic.level}</b>
                </div>
                {result.synced_diagnostic.teacher_topic ? (
                  <div style={{ marginTop: 4, color: "#666" }}>
                    Chủ đề: <b>{result.synced_diagnostic.teacher_topic}</b>
                  </div>
                ) : null}
                {result.synced_diagnostic.plan_id ? (
                  <div style={{ marginTop: 8 }}>
                    ✅ Máy đã tự tạo Learning Path & giao bài tập theo trình độ.
                    <div style={{ marginTop: 8 }}>
                      <Link to="/learning-path" style={{ textDecoration: "none" }}>
                        <button style={{ padding: "8px 12px" }}>Mở Learning Path</button>
                      </Link>
                    </div>
                  </div>
                ) : (
                  <div style={{ marginTop: 8, color: "#666" }}>
                    (Chưa tạo được Learning Path tự động — bạn vẫn có thể vào Learning Path để tạo.)
                  </div>
                )}
              </div>
            )}
          </div>

          <div style={{ background: "#fff", border: "1px solid #eee", borderRadius: 12, padding: 12 }}>
            <div style={{ fontWeight: 900, marginBottom: 10 }}>Breakdown theo độ khó</div>
            {Object.entries(difficultyStats).map(([name, stats]) => {
              const pct = stats.total > 0 ? Math.round((stats.correct / stats.total) * 100) : 0;
              return (
                <div key={name} style={{ marginBottom: 10 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ textTransform: "capitalize" }}>{name}</span>
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
