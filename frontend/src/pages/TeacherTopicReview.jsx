import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiJson } from "../lib/api";

export default function TeacherTopicReview() {
  const { docId } = useParams();
  const [topics, setTopics] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const loadTopics = async () => {
    if (!docId) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiJson(`/documents/${docId}/topics`);
      const list = Array.isArray(data?.topics) ? data.topics : [];
      setTopics(
        list.map((t) => ({
          ...t,
          include: Boolean(t.is_active ?? true),
          titleDraft: t.title || "",
        }))
      );
    } catch (e) {
      setError(e?.message || "Không tải được topics");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTopics();
  }, [docId]);

  const toggleInclude = (topicId, include) => {
    setTopics((prev) => prev.map((t) => (t.topic_id === topicId ? { ...t, include } : t)));
  };

  const updateTitle = (topicId, titleDraft) => {
    setTopics((prev) => prev.map((t) => (t.topic_id === topicId ? { ...t, titleDraft } : t)));
  };

  const publish = async () => {
    setSaving(true);
    setError("");
    try {
      await apiJson(`/documents/${docId}/topics/confirm`, {
        method: "PATCH",
        body: {
          topics: topics.map((t) => ({
            topic_id: t.topic_id,
            include: Boolean(t.include),
            title: (t.titleDraft || "").trim() || undefined,
          })),
        },
      });
      await loadTopics();
    } catch (e) {
      setError(e?.message || "Publish thất bại");
    } finally {
      setSaving(false);
    }
  };

  const activeCount = useMemo(() => topics.filter((t) => t.include).length, [topics]);

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: 16 }}>
      <h2>Teacher Topic Review & Publish</h2>
      {error && <div style={{ color: "#b71c1c", marginBottom: 8 }}>{error}</div>}

      {loading && <div>Đang tải…</div>}
      {!loading && (
        <>
          <div style={{ marginBottom: 12, color: "#555" }}>
            Tổng topics: {topics.length} · Được publish: {activeCount}
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>Include</th>
                <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>Title</th>
                <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>Summary</th>
              </tr>
            </thead>
            <tbody>
              {topics.map((t) => (
                <tr key={t.topic_id}>
                  <td style={{ padding: 8, borderBottom: "1px solid #f0f0f0" }}>
                    <input type="checkbox" checked={Boolean(t.include)} onChange={(e) => toggleInclude(t.topic_id, e.target.checked)} />
                  </td>
                  <td style={{ padding: 8, borderBottom: "1px solid #f0f0f0" }}>
                    <input
                      value={t.titleDraft || ""}
                      onChange={(e) => updateTitle(t.topic_id, e.target.value)}
                      style={{ width: "100%" }}
                    />
                  </td>
                  <td style={{ padding: 8, borderBottom: "1px solid #f0f0f0", color: "#555" }}>
                    {String(t.summary || "").slice(0, 220) || "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
            <button disabled={saving || !topics.length} onClick={publish}>{saving ? "Đang publish..." : "Publish"}</button>
            <Link to="/teacher/files">← Quay lại thư viện</Link>
          </div>
        </>
      )}
    </div>
  );
}
