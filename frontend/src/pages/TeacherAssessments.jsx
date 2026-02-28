import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiJson } from "../lib/api";

export default function TeacherAssessments() {
  // ---- Classroom scope (mỗi lớp một bộ bài kiểm tra)
  const [classrooms, setClassrooms] = useState([]);
  const [classroomId, setClassroomId] = useState(() => {
    const v = localStorage.getItem("teacher_active_classroom_id");
    const n = v ? Number(v) : null;
    return Number.isFinite(n) && n > 0 ? n : null;
  });

  const [title, setTitle] = useState("Bài tổng hợp đầu vào");
  const [level, setLevel] = useState("beginner");
  const [kind, setKind] = useState("diagnostic_pre");
  const [easy, setEasy] = useState(5);
  const [hard, setHard] = useState(2);

  // Documents + topics picker
  const [docs, setDocs] = useState([]);
  const [selectedDocIds, setSelectedDocIds] = useState([]);
  const [topicsByDoc, setTopicsByDoc] = useState({});
  const [selectedTopics, setSelectedTopics] = useState([]);

  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState(null);
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const classroomMap = useMemo(() => {
    const m = new Map();
    (classrooms || []).forEach((c) => m.set(Number(c.id), c));
    return m;
  }, [classrooms]);

  const loadClassrooms = async () => {
    try {
      const rows = await apiJson("/teacher/classrooms");
      const arr = Array.isArray(rows) ? rows : [];
      setClassrooms(arr);
      if (!classroomId && arr.length > 0) {
        setClassroomId(Number(arr[0].id));
      }
    } catch {
      // ignore
    }
  };

  const loadDocs = async () => {
    try {
      const data = await apiJson("/documents");
      const arr = data?.documents || [];
      setDocs(Array.isArray(arr) ? arr : []);
    } catch {
      // ignore
    }
  };

  const loadList = async (cid = classroomId) => {
    if (!cid) {
      setList([]);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await apiJson(`/teacher/assessments?classroom_id=${Number(cid)}`);
      setList(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(e?.message || "Không load được danh sách");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadClassrooms();
    loadDocs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (classroomId) {
      localStorage.setItem("teacher_active_classroom_id", String(classroomId));
      loadList(classroomId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classroomId]);

  // Fetch topics for selected documents
  useEffect(() => {
    (async () => {
      const missing = (selectedDocIds || []).filter((id) => !topicsByDoc[id]);
      if (missing.length === 0) return;
      try {
        const entries = await Promise.all(
          missing.map(async (id) => {
            const data = await apiJson(`/documents/${id}/topics`);
            return [id, data?.topics || []];
          })
        );
        setTopicsByDoc((prev) => {
          const next = { ...(prev || {}) };
          for (const [id, topics] of entries) next[id] = topics;
          return next;
        });
      } catch {
        // ignore
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDocIds]);

  const effectiveDocIds = useMemo(() => {
    return (selectedDocIds || []).map((x) => Number(x)).filter((n) => Number.isFinite(n) && n > 0);
  }, [selectedDocIds]);

  const effectiveTopics = useMemo(() => {
    return (selectedTopics || []).map((s) => String(s)).filter(Boolean);
  }, [selectedTopics]);

  const createAssessment = async () => {
    if (!classroomId) {
      setError("Bạn cần chọn lớp trước khi tạo bài.");
      return;
    }
    setCreating(true);
    setError("");
    setCreated(null);
    try {
      const data = await apiJson("/assessments/generate", {
        method: "POST",
        body: {
          classroom_id: Number(classroomId),
          title,
          level,
          kind,
          easy_count: Number(easy),
          hard_count: Number(hard),
          document_ids: effectiveDocIds,
          topics: effectiveTopics,
        },
      });
      setCreated(data);
      await loadList(classroomId);
    } catch (e) {
      setError(e?.message || "Tạo bài thất bại");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", padding: 16 }}>
      <h2>👩‍🏫 Quản lý bài test tổng hợp (theo lớp)</h2>
      <p style={{ color: "#555", marginTop: 0 }}>
        Dễ: trắc nghiệm (tự chấm). Khó: tự luận (có rubric, có thể auto-grade nếu bật).
      </p>

      <div style={{ background: "#fff", padding: 12, borderRadius: 12, boxShadow: "0 2px 10px rgba(0,0,0,0.06)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <div style={{ fontWeight: 900 }}>Tạo bài mới</div>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <span style={{ color: "#666" }}>Lớp:</span>
            <select
              value={classroomId || ""}
              onChange={(e) => setClassroomId(e.target.value ? Number(e.target.value) : null)}
              style={{ padding: 8, borderRadius: 10, border: "1px solid #ddd" }}
            >
              <option value="">-- Chọn lớp --</option>
              {(classrooms || []).map((c) => (
                <option key={c.id} value={c.id}>
                  #{c.id} • {c.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr 1fr", gap: 12, marginTop: 12 }}>
          <div>
            <label style={{ display: "block", fontWeight: 700 }}>Tiêu đề</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #ddd" }} />
          </div>

          <div>
            <label style={{ display: "block", fontWeight: 700 }}>Loại bài</label>
            <select value={kind} onChange={(e) => setKind(e.target.value)} style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #ddd" }}>
              <option value="diagnostic_pre">Diagnostic PRE (đầu vào)</option>
              <option value="midterm">Giữa khóa</option>
              <option value="diagnostic_post">Diagnostic POST (cuối khóa)</option>
            </select>
          </div>

          <div>
            <label style={{ display: "block", fontWeight: 700 }}>Level</label>
            <select value={level} onChange={(e) => setLevel(e.target.value)} style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #ddd" }}>
              <option value="beginner">Beginner</option>
              <option value="intermediate">Intermediate</option>
              <option value="advanced">Advanced</option>
            </select>
          </div>

          <div>
            <label style={{ display: "block", fontWeight: 700 }}>Easy (MCQ)</label>
            <input type="number" value={easy} onChange={(e) => setEasy(e.target.value)} min={1} style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #ddd" }} />
          </div>

          <div>
            <label style={{ display: "block", fontWeight: 700 }}>Hard (Essay)</label>
            <input type="number" value={hard} onChange={(e) => setHard(e.target.value)} min={0} style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #ddd" }} />
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
          <div>
            <label style={{ display: "block", fontWeight: 700 }}>Chọn tài liệu</label>
            <div style={{ marginTop: 8, display: "grid", gap: 8, maxHeight: 180, overflow: "auto", border: "1px solid #eee", borderRadius: 10, padding: 10 }}>
              {(docs || []).length === 0 && <div style={{ color: "#666" }}>Chưa có tài liệu. Hãy Upload trước.</div>}
              {(docs || []).map((d) => {
                const checked = (selectedDocIds || []).includes(Number(d.document_id));
                return (
                  <label key={d.document_id} style={{ display: "flex", gap: 10, alignItems: "center" }}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => {
                        const id = Number(d.document_id);
                        setSelectedDocIds((prev) => {
                          const cur = Array.isArray(prev) ? prev : [];
                          if (cur.includes(id)) return cur.filter((x) => x !== id);
                          return [...cur, id];
                        });
                      }}
                    />
                    <span>
                      <b>{d.title}</b> <span style={{ color: "#666" }}>(id={d.document_id})</span>
                    </span>
                  </label>
                );
              })}
            </div>
            <div style={{ color: "#666", marginTop: 6 }}>
              Không bắt buộc: nếu bạn không chọn tài liệu/topic, hệ thống sẽ cố gắng ra đề theo title.
            </div>
          </div>

          <div>
            <label style={{ display: "block", fontWeight: 700 }}>Chọn topic (tự động từ tài liệu)</label>
            <div style={{ marginTop: 8, display: "grid", gap: 8, maxHeight: 180, overflow: "auto", border: "1px solid #eee", borderRadius: 10, padding: 10 }}>
              {effectiveDocIds.length === 0 && <div style={{ color: "#666" }}>Chọn ít nhất 1 tài liệu để hiện topic.</div>}
              {effectiveDocIds.length > 0 && (
                <>
                  {effectiveDocIds.flatMap((did) => {
                    const tps = topicsByDoc[did] || [];
                    const docTitle = (docs || []).find((x) => Number(x.document_id) === Number(did))?.title || `Doc ${did}`;
                    return (tps || []).map((t) => {
                      const key = `${did}::${t.topic_id || t.title}`;
                      const checked = (selectedTopics || []).includes(String(t.title));
                      const no = Number.isFinite(Number(t.topic_index)) ? Number(t.topic_index) + 1 : null;
                      return (
                        <label key={key} style={{ display: "flex", gap: 10, alignItems: "center" }}>
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => {
                              const title = String(t.title);
                              setSelectedTopics((prev) => {
                                const cur = Array.isArray(prev) ? prev : [];
                                if (cur.includes(title)) return cur.filter((x) => x !== title);
                                return [...cur, title];
                              });
                            }}
                          />
                          <span>
                            <span style={{ color: "#666" }}>{docTitle}{no ? ` — Chủ đề ${no}:` : ":"}</span> {t.title}
                          </span>
                        </label>
                      );
                    });
                  })}
                  {effectiveDocIds.length > 0 && (effectiveDocIds.flatMap((did) => topicsByDoc[did] || []).length === 0) && (
                    <div style={{ color: "#666" }}>Tài liệu chưa có topic tự động. Bạn có thể bỏ trống để ra đề theo title.</div>
                  )}
                </>
              )}
            </div>
            <div style={{ color: "#666", marginTop: 6 }}>
              Có thể chọn 1 hoặc nhiều topic để ra đề bám sát trọng tâm.
            </div>
          </div>
        </div>

        <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 12 }}>
          <button onClick={createAssessment} disabled={creating} style={{ padding: "10px 14px" }}>
            Tạo bài
          </button>
          {creating && <span style={{ color: "#666" }}>Đang tạo…</span>}
        </div>

        {error && <div style={{ marginTop: 12, background: "#fff3f3", border: "1px solid #ffd0d0", padding: 12, borderRadius: 12 }}>{error}</div>}

        {created && (
          <div style={{ marginTop: 12, background: "#f6ffed", border: "1px solid #b7eb8f", padding: 12, borderRadius: 12 }}>
            <div style={{ fontWeight: 900 }}>✅ Tạo thành công</div>
            <div>Assessment ID: {created.assessment_id}</div>
            <div style={{ display: "flex", gap: 10, marginTop: 8, flexWrap: "wrap" }}>
              <Link to={`/teacher/assessments/${created.assessment_id}/leaderboard`} style={{ textDecoration: "none" }}>
                <button style={{ padding: "8px 12px" }}>Xem leaderboard</button>
              </Link>
            </div>
          </div>
        )}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 18, flexWrap: "wrap", gap: 10 }}>
        <h3 style={{ margin: 0 }}>Danh sách bài của lớp</h3>
        <button onClick={() => loadList(classroomId)} disabled={loading || !classroomId} style={{ padding: "8px 12px" }}>
          Refresh
        </button>
      </div>

      {loading && <div style={{ color: "#666", marginTop: 8 }}>Đang tải…</div>}

      <div style={{ display: "grid", gap: 12, marginTop: 12 }}>
        {list.map((it) => {
          const cls = classroomMap.get(Number(it.classroom_id));
          const classLabel = cls ? `#${cls.id} • ${cls.name}` : `#${it.classroom_id}`;
          return (
            <div key={it.assessment_id} style={{ background: "#fff", borderRadius: 12, padding: 12, boxShadow: "0 2px 10px rgba(0,0,0,0.06)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                <div>
                  <div style={{ fontWeight: 900 }}>{it.title}</div>
                  <div style={{ color: "#666" }}>
                    Lớp: {classLabel} • Kind: {it.kind} • Level: {it.level} • Created: {it.created_at}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 10 }}>
                  <Link to={`/teacher/assessments/${it.assessment_id}/leaderboard`} style={{ textDecoration: "none" }}>
                    <button style={{ padding: "8px 12px" }}>Leaderboard</button>
                  </Link>
                </div>
              </div>
            </div>
          );
        })}

        {!loading && (!classroomId ? <div style={{ color: "#666" }}>Chọn lớp để xem danh sách.</div> : list.length === 0 ? <div style={{ color: "#666" }}>Chưa có bài nào.</div> : null)}
      </div>
    </div>
  );
}
