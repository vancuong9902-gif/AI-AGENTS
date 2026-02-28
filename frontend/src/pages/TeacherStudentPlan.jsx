import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { apiJson } from "../lib/api";

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

export default function TeacherStudentPlan() {
  const { studentId } = useParams();
  const [sp] = useSearchParams();
  const classroomId = sp.get("classroom_id") || "";

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  const plan = data?.plan || null;
  const days = useMemo(() => {
    const ds = (plan?.days || []).slice();
    ds.sort((a, b) => Number(a.day_index) - Number(b.day_index));
    return ds;
  }, [plan]);

  const submissions = data?.homework_submissions || {};

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const q = classroomId ? `?classroom_id=${encodeURIComponent(classroomId)}` : "";
        const resp = await apiJson(`/learning-plans/${studentId}/latest${q}`);
        setData(resp || null);
      } catch (e) {
        setError(String(e?.message || e));
      } finally {
        setLoading(false);
      }
    })();
  }, [studentId, classroomId]);

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", padding: 16 }}>
      <div style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>👩‍🏫 Learning Path của học sinh</h2>
        <div style={{ color: "#666", marginTop: 4 }}>
          Student ID: <strong>{studentId}</strong>
          {classroomId && (
            <>
              {" "}• Classroom ID: <strong>{classroomId}</strong>
            </>
          )}
        </div>
        <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap" }}>
          {classroomId ? (
            <Link to={`/teacher/classrooms/${classroomId}`} style={{ textDecoration: "none" }}>
              ← Quay lại lớp
            </Link>
          ) : (
            <Link to={`/teacher/classrooms`} style={{ textDecoration: "none" }}>
              ← Quay lại danh sách lớp
            </Link>
          )}
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: 12, padding: 10, border: "1px solid #ffa39e", background: "#fff1f0", borderRadius: 10 }}>
          {error}
        </div>
      )}
      {loading && <div style={{ color: "#666" }}>Đang tải…</div>}

      {!plan ? (
        <div style={{ border: "1px solid #eee", borderRadius: 14, padding: 16, background: "#fff", color: "#666" }}>
          Học sinh chưa có Learning Plan được lưu.
        </div>
      ) : (
        <>
          <div style={{ border: "1px solid #eee", borderRadius: 14, padding: 16, background: "#fff", marginBottom: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <div>
                <div>
                  <strong>Chủ đề:</strong> {plan.assigned_topic || "(không có)"}
                </div>
                <div>
                  <strong>Mức độ:</strong> {plan.level || "(không có)"}
                </div>
              </div>
              <div>
                <strong>Plan ID:</strong> {data?.plan_id}
              </div>
            </div>
            {plan.summary && (
              <div style={{ marginTop: 10, color: "#555", whiteSpace: "pre-wrap" }}>
                <strong>Tóm tắt:</strong> {plan.summary}
              </div>
            )}
          </div>

          <div style={{ display: "grid", gap: 10 }}>
            {(days || []).map((d) => {
              const sub = submissions?.[d.day_index] || null;
              const grade = sub?.grade || null;
              const score = Number(grade?.score_points || 0);
              const max = Number(grade?.max_points || 0);
              const hasSub = !!sub;

              return (
                <details
                  key={d.day_index}
                  style={{ border: "1px solid #eee", borderRadius: 14, padding: 12, background: "#fff" }}
                >
                  <summary style={{ cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                    <div style={{ fontWeight: 900 }}>
                      Bài {d.day_index}: {d.title}
                      {!hasSub && <span style={{ marginLeft: 10, color: "#999", fontWeight: 600 }}>(chưa nộp)</span>}
                    </div>
                    {hasSub && <ScorePill score={score} max={max} />}
                  </summary>

                  {!!(d.objectives || []).length && (
                    <ul style={{ margin: "10px 0 0 20px", color: "#555" }}>
                      {(d.objectives || []).map((o, idx) => (
                        <li key={idx}>{o}</li>
                      ))}
                    </ul>
                  )}

                  {d.lesson_md && (
                    <div style={{ marginTop: 10 }}>
                      <div style={{ fontWeight: 800, marginBottom: 6 }}>📘 Bài học</div>
                      <pre
                        style={{
                          whiteSpace: "pre-wrap",
                          padding: 12,
                          borderRadius: 12,
                          border: "1px solid #eee",
                          background: "#fcfcff",
                        }}
                      >
                        {d.lesson_md}
                      </pre>
                    </div>
                  )}

                  <div style={{ marginTop: 10 }}>
                    <div style={{ fontWeight: 800, marginBottom: 6 }}>🏠 Bài tập về nhà</div>
                    {!hasSub ? (
                      <div style={{ color: "#666" }}>Chưa có bài nộp.</div>
                    ) : (
                      <>
                        {grade?.comment && (
                          <div style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>
                            <strong>Nhận xét:</strong> {grade.comment}
                          </div>
                        )}

                        {!!(grade?.mcq_breakdown || []).length && (
                          <div style={{ marginTop: 10 }}>
                            <div style={{ fontWeight: 700 }}>Trắc nghiệm</div>
                            <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
                              {(grade.mcq_breakdown || []).map((q, idx) => {
                                const chosen = q?.chosen_index;
                                const correct = q?.correct_index;
                                const opts = q?.options || [];
                                return (
                                  <div key={idx} style={{ border: "1px solid #eee", borderRadius: 12, padding: 10 }}>
                                    <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                                      <strong>Câu {idx + 1}</strong>
                                      <span style={{ fontWeight: 800 }}>
                                        {q.score_points}/{q.max_points}đ
                                      </span>
                                    </div>
                                    <div style={{ marginTop: 6 }}>{q.stem}</div>
                                    <div style={{ marginTop: 6, color: "#555" }}>
                                      <div>
                                        <strong>Học sinh chọn:</strong> {chosen === null || chosen === undefined ? "(bỏ trống)" : `${String.fromCharCode(65 + Number(chosen))}. ${opts?.[chosen] || ""}`}
                                      </div>
                                      <div>
                                        <strong>Đáp án đúng:</strong> {correct === null || correct === undefined ? "(không rõ)" : `${String.fromCharCode(65 + Number(correct))}. ${opts?.[correct] || ""}`}
                                      </div>
                                    </div>
                                    {q.explanation && (
                                      <div style={{ marginTop: 6, color: "#555" }}>
                                        <strong>Giải thích:</strong> {q.explanation}
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {!!(grade?.rubric_breakdown || []).length && (
                          <div style={{ marginTop: 12 }}>
                            <div style={{ fontWeight: 700 }}>Tự luận (Rubric)</div>
                            <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
                              {(grade.rubric_breakdown || []).map((r, idx) => (
                                <div key={idx} style={{ border: "1px solid #eee", borderRadius: 12, padding: 10 }}>
                                  <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                                    <strong>{r.criterion}</strong>
                                    <span style={{ fontWeight: 800 }}>
                                      {r.score}/{r.max}
                                    </span>
                                  </div>
                                  {r.feedback && <div style={{ color: "#555", marginTop: 6 }}>{r.feedback}</div>}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {sub?.answer_text && (
                          <div style={{ marginTop: 12 }}>
                            <div style={{ fontWeight: 700, marginBottom: 6 }}>Bài tự luận học sinh nộp</div>
                            <pre style={{ whiteSpace: "pre-wrap", padding: 12, borderRadius: 12, border: "1px solid #eee", background: "#fff" }}>
                              {sub.answer_text}
                            </pre>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </details>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
