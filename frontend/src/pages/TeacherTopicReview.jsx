import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiJson } from "../lib/api";

export default function TeacherTopicReview() {
  const { docId } = useParams();
  const [topics, setTopics] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [pagination, setPagination] = useState({ total: 0, limit: 20, offset: 0 });

  const loadTopics = useCallback(async () => {
    if (!docId) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiJson(`/documents/${docId}/topics?limit=20&offset=0`);
      const list = Array.isArray(data?.items) ? data.items : Array.isArray(data?.topics) ? data.topics : [];
      setTopics(
        list.map((t) => ({
          ...t,
          include: Boolean(t.is_active ?? true),
          titleDraft: t.title || "",
        }))
      );
      setPagination({
        total: Number(data?.total || list.length),
        limit: Number(data?.limit || 20),
        offset: Number(data?.offset || 0),
      });
    } catch (e) {
      setError(e?.message || "Không tải được topics");
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    loadTopics();
  }, [loadTopics]);

  const loadMore = async () => {
    if (!docId) return;
    setLoadingMore(true);
    setError("");
    try {
      const nextOffset = pagination.offset + pagination.limit;
      const data = await apiJson(`/documents/${docId}/topics?limit=${pagination.limit}&offset=${nextOffset}`);
      const list = Array.isArray(data?.items) ? data.items : Array.isArray(data?.topics) ? data.topics : [];
      const normalized = list.map((t) => ({
        ...t,
        include: Boolean(t.is_active ?? true),
        titleDraft: t.title || "",
      }));
      setTopics((prev) => [...prev, ...normalized]);
      setPagination({
        total: Number(data?.total || pagination.total),
        limit: Number(data?.limit || pagination.limit),
        offset: Number(data?.offset || nextOffset),
      });
    } catch (e) {
      setError(e?.message || "Không tải thêm topics");
    } finally {
      setLoadingMore(false);
    }
  };

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
            {topics.length < pagination.total ? (<button disabled={loadingMore} onClick={loadMore}>{loadingMore ? "Đang tải thêm..." : `Load more (${topics.length}/${pagination.total})`}</button>) : null}
            <button disabled={saving || !topics.length} onClick={publish}>{saving ? "Đang publish..." : "Publish"}</button>
            <Link to="/teacher/files">← Quay lại thư viện</Link>
          </div>
        </>
      )}
    </div>
  );
}
