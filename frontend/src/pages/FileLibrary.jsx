import { useEffect, useState } from "react";
import { apiJson } from "../lib/api";

export default function FilesPage() {
  const [docs, setDocs] = useState([]);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  // Topic viewer (teacher uses this to inspect topic outlines and study-ready summaries)
  const [topicsOpen, setTopicsOpen] = useState({}); // { [docId]: bool }
  const [topicsByDoc, setTopicsByDoc] = useState({}); // { [docId]: topics[] }
  const [topicsLoading, setTopicsLoading] = useState({});
  const [guideOpen, setGuideOpen] = useState({}); // { [docId:topicKey]: bool }

  const [editingId, setEditingId] = useState(null);
  const [editTitle, setEditTitle] = useState("");
  const [editTags, setEditTags] = useState("");

  const refresh = async () => {
    const data = await apiJson("/documents");
    setDocs(data?.documents || []);
  };

  const loadTopics = async (document_id, force = false) => {
    const did = Number(document_id);
    if (!force && topicsByDoc[did]) return;
    setTopicsLoading((p) => ({ ...(p || {}), [did]: true }));
    try {
      const data = await apiJson(`/documents/${did}/topics?detail=1`);
      setTopicsByDoc((p) => ({ ...(p || {}), [did]: data?.topics || [] }));
    } finally {
      setTopicsLoading((p) => ({ ...(p || {}), [did]: false }));
    }
  };

  const toggleTopics = async (document_id) => {
    const did = Number(document_id);
    setTopicsOpen((p) => ({ ...(p || {}), [did]: !p?.[did] }));
    // lazy load
    if (!topicsByDoc[did]) await loadTopics(did);
  };

  const toggleGuide = (key) => {
    setGuideOpen((p) => ({ ...(p || {}), [key]: !p?.[key] }));
  };

  const regenerateTopics = async (document_id) => {
    const did = Number(document_id);
    try {
      setMsg("Đang regenerate topics...");
      await apiJson(`/documents/${did}/topics/regenerate`, { method: "POST" });
      await loadTopics(did, true);
      await refresh();
      setMsg("✅ Đã regenerate topics.");
    } catch (e) {
      setMsg(e?.message || "Không regenerate được");
    }
  };

  useEffect(() => {
    (async () => {
      try {
        await refresh();
      } catch (e) {
        setError(e?.message || "Không kết nối được backend");
      }
    })();
  }, []);

  const startEdit = (d) => {
    setEditingId(d.document_id);
    setEditTitle(d.title || "");
    setEditTags(Array.isArray(d.tags) ? d.tags.join(", ") : "");
    setMsg("");
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditTitle("");
    setEditTags("");
  };

  const saveEdit = async (document_id) => {
    try {
      setMsg("Đang lưu...");
      await apiJson(`/documents/${document_id}`, {
        method: "PUT",
        body: {
          title: editTitle,
          tags: editTags,
        },
      });
      await refresh();
      setMsg("Đã cập nhật tài liệu.");
      cancelEdit();
    } catch (e) {
      setMsg(e?.message || "Không cập nhật được");
    }
  };

  const deleteDoc = async (document_id) => {
    const ok = window.confirm("Xóa tài liệu này? (Sẽ xóa chunks/topics liên quan)");
    if (!ok) return;
    try {
      setMsg("Đang xóa...");
      await apiJson(`/documents/${document_id}`, { method: "DELETE" });
      await refresh();
      setMsg("Đã xóa tài liệu.");
    } catch (e) {
      setMsg(e?.message || "Không xóa được");
    }
  };

  return (
    <div style={{ padding: 20 }}>
      <h2>📚 Thư viện tài liệu (DB)</h2>
      {error && <p style={{ color: "#b00020" }}>{error}</p>}
      {msg && <p style={{ opacity: 0.85 }}>{msg}</p>}

      {docs.length === 0 && !error && <p>Chưa có tài liệu nào (hãy Upload trước).</p>}

      <ul>
        {docs.map((d) => (
          <li key={d.document_id} style={{ marginBottom: 8 }}>
            <div>
              📄 <b>{d.title}</b> <span style={{ opacity: 0.75 }}>({d.filename})</span>
            </div>
            <div style={{ opacity: 0.75 }}>
              id={d.document_id} · chunks={d.chunk_count} · tags={Array.isArray(d.tags) ? d.tags.join(", ") : ""}
            </div>

            <div style={{ marginTop: 6, display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button onClick={() => startEdit(d)}>
                Sửa
              </button>
              <button onClick={() => toggleTopics(d.document_id)}>
                {topicsOpen?.[d.document_id] ? "Ẩn topics" : "Xem topics"}
              </button>
              <button onClick={() => regenerateTopics(d.document_id)} title="Re-run topic extraction" style={{ background: "#f6ffed" }}>
                Regenerate
              </button>
              <button onClick={() => deleteDoc(d.document_id)} style={{ background: "#ffe6e6" }}>
                Xóa
              </button>
            </div>

            {topicsOpen?.[d.document_id] && (
              <div style={{ marginTop: 10, padding: 12, border: "1px solid #eee", borderRadius: 12, background: "#fafafa" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <div style={{ fontWeight: 900 }}>Topic outline (học & ra đề)</div>
                  {topicsLoading?.[d.document_id] ? <div style={{ color: "#666" }}>Đang tải…</div> : null}
                </div>

                {(topicsByDoc[d.document_id] || []).length === 0 && !topicsLoading?.[d.document_id] ? (
                  <div style={{ color: "#666", marginTop: 6 }}>Chưa có topics cho tài liệu này.</div>
                ) : (
                  <div style={{ display: "grid", gap: 10, marginTop: 10 }}>
                    {(topicsByDoc[d.document_id] || []).map((t) => {
                      const label = t.display_title || t.title;
                      const tkey = `${d.document_id}:${t.topic_id || label}`;
                      return (
                        <div key={t.topic_id || label} style={{ background: "#fff", border: "1px solid #eee", borderRadius: 12, padding: 12 }}>
                          <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                            <div style={{ fontWeight: 900 }}>{label}</div>
                            {t.quiz_ready ? (
                              <span style={{ fontSize: 12, fontWeight: 900, padding: "4px 10px", borderRadius: 999, background: "#f6ffed", border: "1px solid #b7eb8f", color: "#237804" }}>
                                Quiz-ready
                              </span>
                            ) : (
                              <span style={{ fontSize: 12, fontWeight: 900, padding: "4px 10px", borderRadius: 999, background: "#fffbe6", border: "1px solid #ffe58f", color: "#ad6800" }}>
                                Ít dữ liệu
                              </span>
                            )}
                          </div>
                          {t.summary ? <div style={{ marginTop: 6, color: "#444" }}>{t.summary}</div> : null}

                          {t.study_guide_md ? (
                            <div style={{ marginTop: 10 }}>
                              <button onClick={() => toggleGuide(tkey)} style={{ background: "#eef5ff" }}>
                                {guideOpen?.[tkey] ? "Ẩn tài liệu" : "Xem tài liệu (Thea-like)"}
                              </button>
                              {guideOpen?.[tkey] ? (
                                <pre style={{ marginTop: 8, whiteSpace: "pre-wrap", fontFamily: "inherit", lineHeight: 1.55, background: "#fafafa", border: "1px solid #eee", borderRadius: 12, padding: 12 }}>
                                  {t.study_guide_md}
                                </pre>
                              ) : null}
                            </div>
                          ) : null}

                          {Array.isArray(t.key_points) && t.key_points.length > 0 ? (
                            <div style={{ marginTop: 8 }}>
                              <div style={{ fontWeight: 800, color: "#555" }}>Ý chính</div>
                              <ul style={{ margin: "6px 0 0 0", paddingLeft: 18 }}>
                                {t.key_points.slice(0, 8).map((x, i) => (
                                  <li key={i} style={{ marginBottom: 2, color: "#333" }}>{x}</li>
                                ))}
                              </ul>
                            </div>
                          ) : null}

                          {Array.isArray(t.definitions) && t.definitions.length > 0 ? (
                            <div style={{ marginTop: 8 }}>
                              <div style={{ fontWeight: 800, color: "#555" }}>Khái niệm</div>
                              <ul style={{ margin: "6px 0 0 0", paddingLeft: 18 }}>
                                {t.definitions.slice(0, 6).map((d, i) => (
                                  <li key={i} style={{ marginBottom: 2, color: "#333" }}>
                                    <b>{d.term}:</b> {d.definition}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {editingId === d.document_id && (
              <div style={{ marginTop: 8, padding: 10, border: "1px solid #eee", borderRadius: 10, maxWidth: 720 }}>
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontWeight: 700 }}>Tiêu đề</div>
                  <input
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #ddd" }}
                  />
                </div>

                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontWeight: 700 }}>Tags (phân tách bằng dấu phẩy)</div>
                  <input
                    value={editTags}
                    onChange={(e) => setEditTags(e.target.value)}
                    placeholder="VD: deep learning, chương 1"
                    style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #ddd" }}
                  />
                </div>

                <div style={{ display: "flex", gap: 8 }}>
                  <button onClick={() => saveEdit(d.document_id)}>
                    Lưu
                  </button>
                  <button onClick={cancelEdit}>
                    Hủy
                  </button>
                </div>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
