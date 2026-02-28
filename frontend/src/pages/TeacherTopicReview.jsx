import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiJson } from "../lib/api";

const badgeStyle = {
  approved: { background: "#e8f5e9", color: "#1b5e20" },
  rejected: { background: "#ffebee", color: "#b71c1c" },
  pending_review: { background: "#fff8e1", color: "#8a6d00" },
  edited: { background: "#e3f2fd", color: "#0d47a1" },
};

export default function TeacherTopicReview() {
  const { docId } = useParams();
  const navigate = useNavigate();
  const [topics, setTopics] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [draftTitles, setDraftTitles] = useState({});

  const loadTopics = async () => {
    if (!docId) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiJson(`/documents/${docId}/topics`);
      const list = Array.isArray(data?.topics) ? data.topics : [];
      setTopics(list);
      setDraftTitles(Object.fromEntries(list.map((t) => [t.topic_id, t.teacher_edited_title || t.title || ""])));
    } catch (e) {
      setError(e?.message || "Không tải được topics");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadTopics(); }, [docId]);

  const updateTopic = async (topicId, payload) => {
    await apiJson(`/documents/${docId}/topics/${topicId}`, { method: "PATCH", body: payload });
    await loadTopics();
  };

  const approveAll = async () => {
    await apiJson(`/documents/${docId}/topics/approve-all`, { method: "POST" });
    await loadTopics();
  };

  const regenerate = async () => {
    await apiJson(`/documents/${docId}/topics/regenerate`, { method: "POST" });
    await loadTopics();
  };

  const pendingCount = useMemo(() => topics.filter((t) => t.status === "pending_review").length, [topics]);
  const approvedCount = useMemo(() => topics.filter((t) => t.status === "approved").length, [topics]);
  const canProceed = pendingCount === 0 && approvedCount > 0;

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: 16 }}>
      <h2>Teacher Review Topics</h2>
      <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
        <button onClick={approveAll}>Approve All</button>
        <button onClick={regenerate}>Regenerate Topics</button>
        <button disabled={!canProceed} onClick={() => navigate("/teacher/assessments")}>Tiến hành tạo bài kiểm tra</button>
      </div>

      {loading && <div>Đang tải…</div>}
      {error && <div style={{ color: "#b71c1c" }}>{error}</div>}

      {!loading && !error && (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>[Topic AI đề xuất]</th>
              <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>[Nội dung mẫu]</th>
              <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>[Trạng thái]</th>
              <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>[Action]</th>
            </tr>
          </thead>
          <tbody>
            {topics.map((t) => (
              <tr key={t.topic_id}>
                <td style={{ padding: 8, borderBottom: "1px solid #f0f0f0" }}>
                  <div style={{ fontWeight: 700 }}>{t.title}</div>
                  <input
                    value={draftTitles[t.topic_id] || ""}
                    onChange={(e) => setDraftTitles((prev) => ({ ...prev, [t.topic_id]: e.target.value }))}
                    placeholder="Chỉnh tên topic"
                    style={{ width: "100%", marginTop: 6 }}
                  />
                </td>
                <td style={{ padding: 8, borderBottom: "1px solid #f0f0f0", color: "#555" }}>{String(t.content_preview || t.summary || "").slice(0, 220) || "-"}</td>
                <td style={{ padding: 8, borderBottom: "1px solid #f0f0f0" }}>
                  <span style={{ padding: "4px 8px", borderRadius: 999, ...(badgeStyle[t.status] || badgeStyle.pending_review) }}>{t.status}</span>
                </td>
                <td style={{ padding: 8, borderBottom: "1px solid #f0f0f0" }}>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <button onClick={() => updateTopic(t.topic_id, { status: "approved" })}>Approve</button>
                    <button onClick={() => updateTopic(t.topic_id, { status: "rejected" })}>Reject</button>
                    <button onClick={() => updateTopic(t.topic_id, { title: draftTitles[t.topic_id], status: "edited" })}>Save Edit</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div style={{ marginTop: 12 }}>
        <Link to="/teacher/files">← Quay lại thư viện</Link>
      </div>
    </div>
  );
}
