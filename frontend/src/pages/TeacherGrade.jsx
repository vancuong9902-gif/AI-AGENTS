import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiJson } from "../lib/api";

// Backend expects integer points (Pydantic int). Some browsers allow decimals in <input type="number">
// so we round to the nearest int to avoid 422 validation errors when teacher enters 7.5, etc.
function clamp(n, min, max) {
  const raw = Number(n);
  const x = Number.isFinite(raw) ? Math.round(raw) : 0;
  if (x < min) return min;
  if (x > max) return max;
  return x;
}

function prettySources(sources) {
  if (!Array.isArray(sources) || sources.length === 0) return null;
  // Common shapes: {chunk_id, document_id} or {doc_id, chunk_id} or free text.
  return sources
    .map((s) => {
      if (!s || typeof s !== "object") return String(s);
      const doc = s.document_id ?? s.doc_id;
      const chunk = s.chunk_id ?? s.chunkId;
      if (doc != null && chunk != null) return `doc ${doc} • chunk ${chunk}`;
      if (chunk != null) return `chunk ${chunk}`;
      return JSON.stringify(s);
    })
    .join(" • ");
}

export default function TeacherGrade() {
  const { id, studentId } = useParams();
  const assessmentId = Number(id);
  const sid = Number(studentId);

  const [submission, setSubmission] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");

  // qid -> {score_points, comment, max_points}
  const [localGrades, setLocalGrades] = useState({});

  const mcqItems = useMemo(() => (submission?.breakdown || []).filter((b) => b.type === "mcq"), [submission]);
  const essayItems = useMemo(() => (submission?.breakdown || []).filter((b) => b.type === "essay"), [submission]);

  const totals = useMemo(() => {
    const bd = submission?.breakdown || [];
    let mcqEarned = 0,
      mcqTotal = 0,
      essayEarned = 0,
      essayTotal = 0,
      pending = false;

    for (const it of bd) {
      const mp = Number(it?.max_points ?? (it?.type === "essay" ? 10 : 1));
      const sp = Number(it?.score_points ?? 0);

      if (it?.type === "mcq") {
        mcqTotal += mp;
        mcqEarned += sp;
      } else if (it?.type === "essay") {
        essayTotal += mp;
        essayEarned += sp;
        if (!it?.graded) pending = true;
      }
    }

    return {
      mcqEarned,
      mcqTotal,
      essayEarned,
      essayTotal,
      totalEarned: mcqEarned + essayEarned,
      totalMax: mcqTotal + essayTotal,
      pending,
    };
  }, [submission]);

  const load = async () => {
    setLoading(true);
    setError("");
    setToast("");

    try {
      const data = await apiJson(`/teacher/assessments/${assessmentId}/submissions/${sid}`, { method: "GET" });
      setSubmission(data);

      // init local grade state from latest breakdown
      const init = {};
      (data.breakdown || []).forEach((b) => {
        if (b.type === "essay") {
          const maxp = Number(b.max_points ?? 10);
          init[b.question_id] = {
            score_points: clamp(b.score_points ?? 0, 0, maxp),
            comment: b.comment ?? "",
            max_points: maxp,
          };
        }
      });
      setLocalGrades(init);
    } catch (e) {
      setError(e?.message || "Không load được bài nộp");
      setSubmission(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (Number.isFinite(assessmentId) && Number.isFinite(sid)) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assessmentId, sid]);

  const updateGrade = (qid, patch) => {
    setLocalGrades((prev) => ({ ...prev, [qid]: { ...(prev[qid] || {}), ...patch } }));
  };

  const hasInvalid = useMemo(() => {
    for (const it of essayItems) {
      const g = localGrades[it.question_id];
      const maxp = Number(it.max_points ?? 10);
      const sp = Number(g?.score_points);
      if (!Number.isFinite(sp)) return true;
      if (sp < 0 || sp > maxp) return true;
    }
    return false;
  }, [essayItems, localGrades]);

  const save = async () => {
    if (!submission) return;
    setSaving(true);
    setError("");
    setToast("");

    try {
      const grades = Object.entries(localGrades).map(([qid, g]) => ({
        question_id: Number(qid),
        score_points: clamp(g.score_points ?? 0, 0, Number(g.max_points ?? 10)),
        comment: (g.comment ?? "").trim() || null,
      }));

      await apiJson(`/teacher/assessments/${assessmentId}/grade`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ student_id: sid, grades }),
      });

      setToast("✅ Đã lưu điểm tự luận");
      await load();
    } catch (e) {
      setError(e?.message || "Lưu điểm thất bại");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <div>
          <h2 style={{ margin: 0 }}>🧑‍🏫 Chấm bài — Student {sid}</h2>
          <div style={{ color: "#666" }}>Assessment {assessmentId}</div>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <Link to={`/teacher/assessments/${assessmentId}/leaderboard`} style={{ textDecoration: "none" }}>
            <button style={{ padding: "8px 12px" }}>⬅ Leaderboard</button>
          </Link>
          <button onClick={load} disabled={loading} style={{ padding: "8px 12px" }}>
            Refresh
          </button>
        </div>
      </div>

      {toast && (
        <div style={{ marginTop: 12, background: "#f6ffed", border: "1px solid #b7eb8f", padding: 12, borderRadius: 12 }}>
          {toast}
        </div>
      )}

      {error && (
        <div style={{ marginTop: 12, background: "#fff3f3", border: "1px solid #ffd0d0", padding: 12, borderRadius: 12 }}>
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ color: "#666", marginTop: 12 }}>Đang tải…</div>
      ) : !submission ? (
        <div style={{ color: "#666", marginTop: 12 }}>Không có submission.</div>
      ) : (
        <>
          <div
            style={{
              marginTop: 12,
              background: "#fff",
              borderRadius: 12,
              padding: 12,
              boxShadow: "0 2px 10px rgba(0,0,0,0.06)",
              display: "grid",
              gridTemplateColumns: "1fr 1fr 1fr 1fr",
              gap: 12,
            }}
          >
            <div>
              <div style={{ color: "#666" }}>Status</div>
              <div style={{ fontWeight: 700 }}>{submission.status}</div>
              {totals.pending && <div style={{ color: "#b36b00", marginTop: 4 }}>Còn câu tự luận chưa chấm</div>}
            </div>
            <div>
              <div style={{ color: "#666" }}>Score %</div>
              <div style={{ fontWeight: 700 }}>{submission.score_percent}</div>
            </div>
            <div>
              <div style={{ color: "#666" }}>Points</div>
              <div style={{ fontWeight: 700 }}>
                {submission.score_points}/{submission.max_points}
              </div>
            </div>
            <div>
              <div style={{ color: "#666" }}>Attempt</div>
              <div style={{ fontWeight: 700 }}>#{submission.attempt_id}</div>
            </div>
          </div>

          <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div style={{ background: "#fff", borderRadius: 12, padding: 12, boxShadow: "0 2px 10px rgba(0,0,0,0.06)" }}>
              <div style={{ fontWeight: 700 }}>MCQ (tự chấm)</div>
              <div style={{ color: "#666", marginTop: 6 }}>
                {totals.mcqEarned}/{totals.mcqTotal} điểm
              </div>
            </div>
            <div style={{ background: "#fff", borderRadius: 12, padding: 12, boxShadow: "0 2px 10px rgba(0,0,0,0.06)" }}>
              <div style={{ fontWeight: 700 }}>Tự luận (giáo viên chấm)</div>
              <div style={{ color: "#666", marginTop: 6 }}>
                {totals.essayEarned}/{totals.essayTotal} điểm
              </div>
            </div>
          </div>

          <h3 style={{ marginTop: 18 }}>Tự luận</h3>
          {essayItems.length === 0 ? (
            <div style={{ color: "#666" }}>Không có câu tự luận.</div>
          ) : (
            <div style={{ display: "grid", gap: 12 }}>
              {essayItems.map((it, idx) => {
                const maxp = Number(it.max_points ?? 10);
                const g = localGrades[it.question_id] || { score_points: 0, comment: "", max_points: maxp };

                const sourcesText = prettySources(it.sources);

                return (
                  <div
                    key={it.question_id}
                    style={{ background: "#fff", borderRadius: 12, padding: 12, boxShadow: "0 2px 10px rgba(0,0,0,0.06)" }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                      <div style={{ fontWeight: 700 }}>Câu TL {idx + 1}</div>
                      <div style={{ color: it.graded ? "#2f7a2f" : "#b36b00" }}>{it.graded ? "✅ Đã chấm" : "⏳ Chưa chấm"}</div>
                    </div>

                    <div style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{it.stem}</div>

                    {sourcesText && (
                      <div style={{ marginTop: 6, color: "#666", fontSize: 13 }}>
                        <b>Sources:</b> {sourcesText}
                      </div>
                    )}

                    <div style={{ marginTop: 10, background: "#fafafa", padding: 10, borderRadius: 10, border: "1px solid #eee" }}>
                      <div style={{ fontWeight: 700, marginBottom: 6 }}>Bài làm của học sinh</div>
                      <div style={{ whiteSpace: "pre-wrap" }}>{it.answer_text || "(trống)"}</div>
                    </div>

                    <details style={{ marginTop: 10 }}>
                      <summary style={{ cursor: "pointer" }}>Rubric</summary>
                      {Array.isArray(it.rubric) && it.rubric.length > 0 ? (
                        <ul style={{ marginTop: 8 }}>
                          {it.rubric.map((r, i) => (
                            <li key={i}>
                              <b>{r.criterion || "Tiêu chí"}</b>
                              {r.points != null ? ` — ${r.points} điểm` : ""}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <div style={{ color: "#666", marginTop: 8 }}>Không có rubric.</div>
                      )}
                    </details>

                    <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 12, flexWrap: "wrap" }}>
                      <label style={{ fontWeight: 600 }}>
                        Điểm:
                        <input
                          type="number"
                          step={1}
                          value={g.score_points}
                          min={0}
                          max={maxp}
                          onChange={(e) => updateGrade(it.question_id, { score_points: Math.round(Number(e.target.value || 0)) })}
                          style={{ marginLeft: 8, width: 110, padding: 8, borderRadius: 8, border: "1px solid #ddd" }}
                        />
                        <span style={{ marginLeft: 6, color: "#666" }}>/ {maxp}</span>
                      </label>

                      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        <button
                          type="button"
                          onClick={() => updateGrade(it.question_id, { score_points: 0 })}
                          style={{ padding: "6px 10px" }}
                        >
                          0
                        </button>
                        <button
                          type="button"
                          onClick={() => updateGrade(it.question_id, { score_points: Math.round(maxp * 0.5) })}
                          style={{ padding: "6px 10px" }}
                        >
                          50%
                        </button>
                        <button
                          type="button"
                          onClick={() => updateGrade(it.question_id, { score_points: maxp })}
                          style={{ padding: "6px 10px" }}
                        >
                          Max
                        </button>
                      </div>

                      <input
                        value={g.comment}
                        onChange={(e) => updateGrade(it.question_id, { comment: e.target.value })}
                        placeholder="Nhận xét (tuỳ chọn)"
                        style={{ flex: 1, minWidth: 220, padding: 8, borderRadius: 8, border: "1px solid #ddd" }}
                      />

                      {hasInvalid && (
                        <div style={{ color: "#b00020" }}>⚠ Điểm không hợp lệ (phải nằm trong 0..{maxp})</div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          <div style={{ marginTop: 16, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <button onClick={save} disabled={saving || essayItems.length === 0 || hasInvalid} style={{ padding: "10px 14px" }}>
              Lưu điểm tự luận
            </button>
            {saving && <span style={{ color: "#666" }}>Đang lưu…</span>}
            <div style={{ color: "#666" }}>
              Tip: sau khi chấm xong, điểm tổng sẽ được cập nhật (MCQ + Tự luận).
            </div>
          </div>

          <details style={{ marginTop: 16 }}>
            <summary style={{ cursor: "pointer" }}>Xem chi tiết MCQ + breakdown</summary>

            {mcqItems.length > 0 && (
              <div style={{ marginTop: 10, background: "#fff", borderRadius: 12, padding: 12, border: "1px solid #eee" }}>
                <div style={{ fontWeight: 700, marginBottom: 8 }}>MCQ</div>
                <div style={{ display: "grid", gap: 10 }}>
                  {mcqItems.map((m, i) => (
                    <div key={m.question_id} style={{ padding: 10, border: "1px solid #f0f0f0", borderRadius: 10 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                        <div style={{ fontWeight: 700 }}>MCQ {i + 1}</div>
                        <div style={{ color: m.is_correct ? "#2f7a2f" : "#b00020" }}>{m.is_correct ? "✅ Đúng" : "❌ Sai"}</div>
                      </div>
                      <div style={{ whiteSpace: "pre-wrap", marginTop: 6 }}>{m.stem}</div>

                      {Array.isArray(m.options) && m.options.length > 0 && (
                        <ol style={{ marginTop: 8 }}>
                          {m.options.map((op, idx) => (
                            <li key={idx} style={{ marginBottom: 4 }}>
                              {op}
                              {idx === m.correct ? " (đáp án)" : ""}
                              {idx === m.chosen ? " (học sinh chọn)" : ""}
                            </li>
                          ))}
                        </ol>
                      )}

                      {m.explanation && (
                        <div style={{ marginTop: 6, color: "#666" }}>
                          <b>Giải thích:</b> {m.explanation}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <pre style={{ whiteSpace: "pre-wrap", marginTop: 12, marginBottom: 0 }}>{JSON.stringify(submission.breakdown, null, 2)}</pre>
          </details>
        </>
      )}
    </div>
  );
}
