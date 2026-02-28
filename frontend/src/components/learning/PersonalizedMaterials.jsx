import { useCallback, useEffect, useMemo, useState } from "react";
import { apiJson } from "../../lib/api";

function weaknessLabel(priority) {
  const p = Number(priority ?? 99);
  if (p <= 2) return { text: "Cần cải thiện nhiều", color: "#dc2626", bg: "#fee2e2" };
  return { text: "Cần ôn thêm", color: "#b45309", bg: "#fef3c7" };
}

export default function PersonalizedMaterials({ studentLevel, recommendations = [], documentId }) {
  const [topics, setTopics] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [expandedTopic, setExpandedTopic] = useState(null);

  const loadTopics = useCallback(async () => {
    if (!documentId) {
      setTopics([]);
      return;
    }

    setLoading(true);
    setError("");
    try {
      const res = await apiJson(`/documents/${documentId}/topics?detail=1`, { method: "GET" });
      const list = Array.isArray(res?.topics) ? res.topics : Array.isArray(res) ? res : [];
      setTopics(list);
    } catch (e) {
      setError(e?.message || "Không tải được danh sách topic");
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    loadTopics();
  }, [loadTopics]);

  const prioritizedTopics = useMemo(() => {
    const recPriorityMap = new Map(
      (recommendations || []).map((item, index) => [String(item?.topic_id || item?.topic || ""), item?.priority ?? index + 1])
    );

    return [...topics]
      .map((topic, index) => {
        const key = String(topic?.topic_id || topic?.id || topic?.title || "");
        const priority = recPriorityMap.get(key) ?? index + 1;
        return { ...topic, _priority: priority };
      })
      .sort((a, b) => Number(a._priority) - Number(b._priority));
  }, [recommendations, topics]);

  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 14, background: "#fff" }}>
      <h3 style={{ marginTop: 0 }}>Tài liệu cá nhân hoá (Mức: {studentLevel || "-"})</h3>

      {loading && <div>Đang tải tài liệu...</div>}
      {error && <div style={{ color: "#dc2626", marginBottom: 8 }}>{error}</div>}

      {!loading && !prioritizedTopics.length && <div style={{ color: "#64748b" }}>Chưa có topic để hiển thị.</div>}

      <div style={{ display: "grid", gap: 10 }}>
        {prioritizedTopics.map((topic, index) => {
          const badge = weaknessLabel(topic?._priority);
          const isExpanded = expandedTopic === (topic?.topic_id || topic?.id || index);
          const topicKey = topic?.topic_id || topic?.id || index;

          return (
            <div key={topicKey} style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "flex-start", flexWrap: "wrap" }}>
                <div>
                  <div style={{ fontWeight: 700 }}>
                    Ưu tiên {index + 1}: {topic?.title || topic?.topic || "(Không tên topic)"}
                  </div>
                  <div style={{ color: "#475569", marginTop: 6 }}>{topic?.summary || "Chưa có tóm tắt."}</div>
                </div>
                <span style={{ borderRadius: 999, padding: "4px 10px", fontSize: 12, fontWeight: 700, color: badge.color, background: badge.bg }}>
                  {badge.text}
                </span>
              </div>

              <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                  type="button"
                  onClick={() => setExpandedTopic(isExpanded ? null : topicKey)}
                  style={{ border: "1px solid #cbd5e1", borderRadius: 8, padding: "8px 12px", background: "#fff" }}
                >
                  {isExpanded ? "Ẩn chi tiết" : "Xem chi tiết"}
                </button>
                <button
                  type="button"
                  style={{ border: 0, borderRadius: 8, padding: "8px 12px", color: "#fff", background: "#16a34a" }}
                >
                  Làm bài tập
                </button>
              </div>

              {isExpanded && (
                <div style={{ marginTop: 10, borderTop: "1px dashed #cbd5e1", paddingTop: 10, color: "#0f172a", whiteSpace: "pre-wrap" }}>
                  {topic?.content || "Nội dung chi tiết sẽ được cập nhật."}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
