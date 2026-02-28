import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiJson } from "../lib/api";

const EXAM_TYPE_OPTIONS = [
  { value: "diagnostic_input", label: "Kiểm tra đầu vào", defaults: { easy: 6, medium: 3, hard: 1, durationMinutes: 30 } },
  { value: "topic_practice", label: "Bài tập theo topic", defaults: { easy: 4, medium: 4, hard: 2, durationMinutes: 45 } },
  { value: "final_exam", label: "Kiểm tra cuối kỳ", defaults: { easy: 5, medium: 6, hard: 4, durationMinutes: 60 } },
];

const DEFAULT_EXAM_TYPE = EXAM_TYPE_OPTIONS[0];

function getTopicLabel(topic, idx) {
  return String(topic?.name || topic?.topic || topic?.title || `Topic ${idx + 1}`).trim();
}

function getTopicPreview(topic) {
  return String(topic?.preview || topic?.content_preview || topic?.snippet || "").trim();
}

function getTopicChunks(topic) {
  const n = Number(topic?.chunk_count ?? topic?.chunks ?? topic?.num_chunks ?? 0);
  return Number.isFinite(n) ? n : 0;
}

function extractQuestions(quiz) {
  if (Array.isArray(quiz?.questions)) return quiz.questions;
  if (Array.isArray(quiz?.items)) return quiz.items;
  if (Array.isArray(quiz?.quiz?.questions)) return quiz.quiz.questions;
  return [];
}

export default function TeacherAssessments() {
  const [classrooms, setClassrooms] = useState([]);
  const [classroomId, setClassroomId] = useState(() => {
    const v = localStorage.getItem("teacher_active_classroom_id");
    const n = v ? Number(v) : null;
    return Number.isFinite(n) && n > 0 ? n : null;
  });

  const [docs, setDocs] = useState([]);
  const [selectedDocIds, setSelectedDocIds] = useState([]);
  const [topicsByDoc, setTopicsByDoc] = useState({});
  const [selectedTopics, setSelectedTopics] = useState([]);
  const [examConfig, setExamConfig] = useState({ examType: DEFAULT_EXAM_TYPE.value, ...DEFAULT_EXAM_TYPE.defaults });
  const [generatedQuiz, setGeneratedQuiz] = useState(null);
  const [diagnosticConfig, setDiagnosticConfig] = useState({ easy: 5, medium: 5, hard: 5 });
  const [diagnosticCreated, setDiagnosticCreated] = useState(null);

  const [creating, setCreating] = useState(false);
  const [assigning, setAssigning] = useState(false);
  const [created, setCreated] = useState(null);
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [topicsLoading, setTopicsLoading] = useState(false);
  const [error, setError] = useState("");

  const classroomMap = useMemo(() => {
    const m = new Map();
    (classrooms || []).forEach((c) => m.set(Number(c.id), c));
    return m;
  }, [classrooms]);

  const effectiveDocIds = useMemo(() => {
    return (selectedDocIds || []).map((x) => Number(x)).filter((n) => Number.isFinite(n) && n > 0);
  }, [selectedDocIds]);

  const allTopics = useMemo(() => {
    return effectiveDocIds.flatMap((docId) => {
      const doc = (docs || []).find((d) => Number(d.document_id) === Number(docId));
      const docTitle = doc?.title || `Document ${docId}`;
      return (topicsByDoc[docId] || []).map((topic, idx) => {
        const name = getTopicLabel(topic, idx);
        return {
          key: `${docId}::${name}`,
          docId,
          docTitle,
          name,
          rawId: Number(topic?.id || topic?.topic_id || topic?.topicId || 0) || null,
          chunkCount: getTopicChunks(topic),
          preview: getTopicPreview(topic),
        };
      });
    });
  }, [effectiveDocIds, topicsByDoc, docs]);

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

  useEffect(() => {
    (async () => {
      if (effectiveDocIds.length === 0) {
        setSelectedTopics([]);
        return;
      }
      const missing = effectiveDocIds.filter((id) => !topicsByDoc[id]);
      if (missing.length === 0) return;
      setTopicsLoading(true);
      try {
        const entries = await Promise.all(
          missing.map(async (id) => {
            const data = await apiJson(`/documents/${id}/topics`);
            const rawTopics = Array.isArray(data) ? data : data?.topics || data?.items || [];
            return [id, rawTopics];
          })
        );
        setTopicsByDoc((prev) => {
          const next = { ...(prev || {}) };
          for (const [id, topics] of entries) next[id] = Array.isArray(topics) ? topics : [];
          return next;
        });
      } catch (e) {
        setError(e?.message || "Không tải được topic từ tài liệu");
      } finally {
        setTopicsLoading(false);
      }
    })();
  }, [effectiveDocIds, topicsByDoc]);

  useEffect(() => {
    setSelectedTopics((prev) => {
      const allowed = new Set(allTopics.map((t) => t.name));
      return (prev || []).filter((t) => allowed.has(t));
    });
  }, [allTopics]);

  const updateExamType = (examType) => {
    const selected = EXAM_TYPE_OPTIONS.find((o) => o.value === examType) || DEFAULT_EXAM_TYPE;
    setExamConfig((prev) => ({ ...prev, examType: selected.value, ...selected.defaults }));
  };

  const createAssessment = async () => {
    if (!classroomId) {
      setError("Bạn cần chọn lớp trước khi tạo bài.");
      return;
    }
    if (selectedTopics.length === 0) {
      setError("Vui lòng chọn ít nhất 1 topic.");
      return;
    }

    setCreating(true);
    setError("");
    setCreated(null);
    setGeneratedQuiz(null);

    try {
      const teacherId = Number(localStorage.getItem("user_id")) || null;
      const body = {
        teacher_id: teacherId,
        classroom_id: Number(classroomId),
        document_ids: effectiveDocIds,
        topics: selectedTopics,
        ...examConfig,
      };

      const data = await apiJson("/lms/generate-quiz", {
        method: "POST",
        body,
      });

      setGeneratedQuiz(data);
      setCreated(data);
      await loadList(classroomId);
    } catch (e) {
      setError(e?.message || "Tạo bài kiểm tra thất bại");
    } finally {
      setCreating(false);
    }
  };

  const assignToClassroom = async () => {
    const quizId = generatedQuiz?.quiz_id || generatedQuiz?.id || generatedQuiz?.assessment_id;
    if (!quizId || !classroomId) {
      setError("Không tìm thấy quiz_id để giao cho lớp.");
      return;
    }
    setAssigning(true);
    setError("");
    try {
      await apiJson("/lms/assign-quiz", {
        method: "POST",
        body: {
          quiz_id: quizId,
          classroom_id: Number(classroomId),
        },
      });
      await loadList(classroomId);
    } catch (e) {
      setError(e?.message || "Giao bài cho lớp thất bại");
    } finally {
      setAssigning(false);
    }
  };

  const createDiagnostic = async () => {
    if (!classroomId) {
      setError("Bạn cần chọn classroom.");
      return;
    }
    const topicIds = allTopics
      .filter((t) => selectedTopicSet.has(t.name))
      .map((t) => Number(t.rawId || t.topicId || 0))
      .filter((n) => Number.isFinite(n) && n > 0);
    if (!topicIds.length) {
      setError("Vui lòng chọn topic hợp lệ để tạo bài đầu vào.");
      return;
    }

    setCreating(true);
    setError("");
    try {
      const data = await apiJson("/assessments/generate-diagnostic", {
        method: "POST",
        body: {
          classroom_id: Number(classroomId),
          topic_ids: topicIds,
          difficulty_config: diagnosticConfig,
        },
      });
      setDiagnosticCreated(data);
      await loadList(classroomId);
    } catch (e) {
      setError(e?.message || "Tạo bài kiểm tra đầu vào thất bại");
    } finally {
      setCreating(false);
    }
  };

  const selectedTopicSet = new Set(selectedTopics);
  const questions = extractQuestions(generatedQuiz);
  const grouped = {
    easy: questions.filter((q) => String(q?.difficulty || q?.level || "").toLowerCase() === "easy"),
    medium: questions.filter((q) => String(q?.difficulty || q?.level || "").toLowerCase() === "medium"),
    hard: questions.filter((q) => String(q?.difficulty || q?.level || "").toLowerCase() === "hard"),
  };

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", padding: 16 }}>
      <h2>👩‍🏫 Quản lý bài kiểm tra theo topic</h2>

      <div style={{ marginTop: 12, background: "#fff", padding: 12, borderRadius: 12, border: "1px solid #e6f4ff" }}>
        <div style={{ fontWeight: 900, marginBottom: 10 }}>Tạo Bài Kiểm Tra Đầu Vào</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: 10 }}>
          {["easy", "medium", "hard"].map((k) => (
            <label key={k} style={{ fontSize: 13 }}>
              {k.toUpperCase()}: <b>{diagnosticConfig[k]}</b>
              <input
                type="range"
                min={1}
                max={10}
                value={diagnosticConfig[k]}
                onChange={(e) => setDiagnosticConfig((prev) => ({ ...prev, [k]: Number(e.target.value) || 1 }))}
                style={{ width: "100%" }}
              />
            </label>
          ))}
        </div>
        <div style={{ marginTop: 8, color: "#555" }}>
          Tổng: <b>{diagnosticConfig.easy + diagnosticConfig.medium + diagnosticConfig.hard} câu</b> | Thời gian ước tính: <b>{(diagnosticConfig.easy + diagnosticConfig.medium + diagnosticConfig.hard) * 2} phút</b>
        </div>
        <div style={{ marginTop: 10 }}>
          <button onClick={createDiagnostic} disabled={creating} style={{ padding: "10px 14px" }}>Tạo bài kiểm tra</button>
        </div>
        {diagnosticCreated?.quiz_set_id ? (
          <div style={{ marginTop: 10, padding: 10, border: "1px solid #b7eb8f", borderRadius: 10, background: "#f6ffed" }}>
            {diagnosticCreated.message} — Link chia sẻ: <Link to={`/assessments/${diagnosticCreated.quiz_set_id}`}>/assessments/{diagnosticCreated.quiz_set_id}</Link>
          </div>
        ) : null}
      </div>


      <div style={{ background: "#fff", padding: 12, borderRadius: 12, boxShadow: "0 2px 10px rgba(0,0,0,0.06)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <div style={{ fontWeight: 900 }}>Flow tạo bài kiểm tra 3 bước</div>
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

        <div style={{ marginTop: 14, border: "1px solid #eee", borderRadius: 10, padding: 12 }}>
          <div style={{ fontWeight: 800, marginBottom: 8 }}>BƯỚC 1 - Chọn tài liệu & topic</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label style={{ display: "block", fontWeight: 700 }}>Danh sách tài liệu PDF</label>
              <div style={{ marginTop: 8, display: "grid", gap: 8, maxHeight: 200, overflow: "auto", border: "1px solid #eee", borderRadius: 10, padding: 10 }}>
                {(docs || []).length === 0 && <div style={{ color: "#666" }}>Chưa có tài liệu. Hãy upload PDF trước.</div>}
                {(docs || []).map((d) => {
                  const id = Number(d.document_id);
                  const checked = (selectedDocIds || []).includes(id);
                  return (
                    <label key={d.document_id} style={{ display: "flex", gap: 10, alignItems: "center" }}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => {
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
            </div>

            <div>
              <label style={{ display: "block", fontWeight: 700 }}>Danh sách topic (GET /api/documents/{'{doc_id}'}/topics)</label>
              <div style={{ display: "flex", gap: 8, marginTop: 8, marginBottom: 8 }}>
                <button
                  type="button"
                  onClick={() => setSelectedTopics(allTopics.map((t) => t.name))}
                  disabled={allTopics.length === 0}
                  style={{ padding: "6px 10px" }}
                >
                  Chọn tất cả
                </button>
                <button type="button" onClick={() => setSelectedTopics([])} disabled={selectedTopics.length === 0} style={{ padding: "6px 10px" }}>
                  Bỏ chọn tất cả
                </button>
              </div>
              <div style={{ marginTop: 8, display: "grid", gap: 8, maxHeight: 220, overflow: "auto", border: "1px solid #eee", borderRadius: 10, padding: 10 }}>
                {effectiveDocIds.length === 0 && <div style={{ color: "#666" }}>Hãy chọn ít nhất 1 tài liệu.</div>}
                {topicsLoading && <div style={{ color: "#666" }}>Đang tải topic…</div>}
                {effectiveDocIds.length > 0 && !topicsLoading && allTopics.length === 0 && <div style={{ color: "#666" }}>Tài liệu chưa có topic.</div>}
                {!topicsLoading &&
                  allTopics.map((tp) => (
                    <label key={tp.key} style={{ display: "block", border: "1px solid #f0f0f0", borderRadius: 8, padding: 8 }}>
                      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        <input
                          type="checkbox"
                          checked={selectedTopicSet.has(tp.name)}
                          onChange={() => {
                            setSelectedTopics((prev) => {
                              const cur = Array.isArray(prev) ? prev : [];
                              if (cur.includes(tp.name)) return cur.filter((x) => x !== tp.name);
                              return [...cur, tp.name];
                            });
                          }}
                        />
                        <div>
                          <b>{tp.name}</b>
                          <div style={{ color: "#666", fontSize: 13 }}>{tp.docTitle}</div>
                        </div>
                      </div>
                      <div style={{ marginTop: 6, color: "#555", fontSize: 13 }}>Chunks: {tp.chunkCount}</div>
                      {tp.preview && <div style={{ marginTop: 4, color: "#666", fontSize: 13 }}>Preview: {tp.preview}</div>}
                    </label>
                  ))}
              </div>
              <div style={{ color: selectedTopics.length > 0 ? "#0f766e" : "#666", marginTop: 8 }}>
                Đã chọn {selectedTopics.length}/{allTopics.length} topic.
              </div>
            </div>
          </div>
        </div>

        {selectedTopics.length > 0 && (
          <div style={{ marginTop: 14, border: "1px solid #eee", borderRadius: 10, padding: 12 }}>
            <div style={{ fontWeight: 800, marginBottom: 8 }}>BƯỚC 2 - Cấu hình bài kiểm tra</div>

            <div>
              <div style={{ fontWeight: 700, marginBottom: 8 }}>Loại bài</div>
              <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
                {EXAM_TYPE_OPTIONS.map((op) => (
                  <label key={op.value} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <input type="radio" checked={examConfig.examType === op.value} onChange={() => updateExamType(op.value)} />
                    {op.label}
                  </label>
                ))}
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(120px,1fr))", gap: 12, marginTop: 10 }}>
              <div>
                <label style={{ display: "block", fontWeight: 700 }}>Easy</label>
                <input
                  type="number"
                  min={0}
                  value={examConfig.easy}
                  onChange={(e) => setExamConfig((prev) => ({ ...prev, easy: Number(e.target.value) || 0 }))}
                  style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #ddd" }}
                />
              </div>
              <div>
                <label style={{ display: "block", fontWeight: 700 }}>Medium</label>
                <input
                  type="number"
                  min={0}
                  value={examConfig.medium}
                  onChange={(e) => setExamConfig((prev) => ({ ...prev, medium: Number(e.target.value) || 0 }))}
                  style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #ddd" }}
                />
              </div>
              <div>
                <label style={{ display: "block", fontWeight: 700 }}>Hard</label>
                <input
                  type="number"
                  min={0}
                  value={examConfig.hard}
                  onChange={(e) => setExamConfig((prev) => ({ ...prev, hard: Number(e.target.value) || 0 }))}
                  style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #ddd" }}
                />
              </div>
              <div>
                <label style={{ display: "block", fontWeight: 700 }}>Thời gian (phút)</label>
                <input
                  type="number"
                  min={5}
                  value={examConfig.durationMinutes}
                  onChange={(e) => setExamConfig((prev) => ({ ...prev, durationMinutes: Number(e.target.value) || 5 }))}
                  style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #ddd" }}
                />
              </div>
            </div>

            <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 12 }}>
              <button onClick={createAssessment} disabled={creating} style={{ padding: "10px 14px" }}>
                Tạo bài kiểm tra
              </button>
              {creating && <span style={{ color: "#666" }}>Đang tạo…</span>}
            </div>
          </div>
        )}

        {generatedQuiz && (
          <div style={{ marginTop: 14, border: "1px solid #d9f7be", background: "#f6ffed", borderRadius: 10, padding: 12 }}>
            <div style={{ fontWeight: 800 }}>BƯỚC 3 - Preview bài kiểm tra</div>
            <div style={{ marginTop: 6, color: "#555" }}>
              Quiz ID: <b>{generatedQuiz?.quiz_id || generatedQuiz?.id || generatedQuiz?.assessment_id || "N/A"}</b>
            </div>

            <div style={{ display: "grid", gap: 10, marginTop: 10 }}>
              {(["easy", "medium", "hard"]).map((lv) => (
                <div key={lv} style={{ border: "1px solid #e5e7eb", borderRadius: 8, background: "#fff", padding: 10 }}>
                  <div style={{ fontWeight: 700, textTransform: "capitalize" }}>{lv} ({grouped[lv].length} câu)</div>
                  {grouped[lv].length === 0 ? (
                    <div style={{ color: "#777", fontSize: 13 }}>Không có câu hỏi.</div>
                  ) : (
                    <ol style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                      {grouped[lv].map((q, idx) => (
                        <li key={`${lv}-${idx}`} style={{ marginBottom: 4 }}>
                          {q?.content || q?.question || q?.text || JSON.stringify(q)}
                        </li>
                      ))}
                    </ol>
                  )}
                </div>
              ))}
            </div>

            <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
              <button onClick={assignToClassroom} disabled={assigning} style={{ padding: "8px 12px" }}>
                {assigning ? "Đang giao..." : "Giao cho lớp"}
              </button>
              <Link to={`/teacher/assessments/${generatedQuiz?.assessment_id || generatedQuiz?.id || ""}/leaderboard`} style={{ textDecoration: "none" }}>
                <button style={{ padding: "8px 12px" }}>Xem kết quả</button>
              </Link>
            </div>
          </div>
        )}

        {error && <div style={{ marginTop: 12, background: "#fff3f3", border: "1px solid #ffd0d0", padding: 12, borderRadius: 12 }}>{error}</div>}

        {created && !generatedQuiz && (
          <div style={{ marginTop: 12, background: "#f6ffed", border: "1px solid #b7eb8f", padding: 12, borderRadius: 12 }}>
            <div style={{ fontWeight: 900 }}>✅ Tạo thành công</div>
            <div>ID: {created.assessment_id || created.id}</div>
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
