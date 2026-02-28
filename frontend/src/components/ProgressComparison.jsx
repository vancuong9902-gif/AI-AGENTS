import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function toPercent(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, Math.round(n)));
}

function levelLabel(value) {
  const raw = String(value || "").trim();
  if (!raw) return "—";
  const map = {
    yeu: "Yếu",
    trung_binh: "Trung bình",
    kha: "Khá",
    gioi: "Giỏi",
    beginner: "Beginner",
    intermediate: "Intermediate",
    advanced: "Advanced",
  };
  return map[raw.toLowerCase()] || raw.toUpperCase();
}

function ProgressRow({ label, pct, level, color }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "90px 1fr auto", gap: 10, alignItems: "center" }}>
      <div style={{ fontWeight: 700 }}>{label}</div>
      <div style={{ height: 14, borderRadius: 999, background: "#e2e8f0", overflow: "hidden" }}>
        <div style={{ width: `${toPercent(pct)}%`, height: "100%", background: color, borderRadius: 999 }} />
      </div>
      <div style={{ fontSize: 13, color: "#334155", whiteSpace: "nowrap" }}>
        {toPercent(pct)}% • <strong>{levelLabel(level)}</strong>
      </div>
    </div>
  );
}

export default function ProgressComparison({ comparison, showTopics = false }) {
  if (!comparison) return null;

  const hasFinal = !!comparison.has_final;
  const improvement = Number(comparison.improvement_pct || 0);
  const improvementText = improvement > 0 ? `+${Math.round(improvement)}%` : `${Math.round(improvement)}%`;
  const diagnosticPct = toPercent(comparison.diagnostic_pct);
  const finalPct = hasFinal ? toPercent(comparison.final_pct) : 50;
  const topics = Array.isArray(comparison.topic_comparison) ? comparison.topic_comparison : [];

  return (
    <div style={{ background: "#fff", borderRadius: 16, padding: 16, border: "1px solid #e2e8f0", display: "grid", gap: 12 }}>
      <h3 style={{ margin: 0 }}>📊 Tiến bộ của bạn</h3>

      <ProgressRow label="Đầu kỳ" pct={diagnosticPct} level={comparison.diagnostic_level} color="#60a5fa" />
      <ProgressRow label="Cuối kỳ" pct={finalPct} level={comparison.final_level} color="#1d4ed8" />

      {!hasFinal ? (
        <div style={{ color: "#64748b", fontWeight: 600 }}>Hoàn thành bài kiểm tra cuối kỳ để thấy tiến bộ của bạn!</div>
      ) : (
        <div style={{ color: improvement >= 0 ? "#166534" : "#b91c1c", fontWeight: 700 }}>
          {improvementText} {improvement >= 15 ? "🚀 Cải thiện đáng kể!" : improvement >= 0 ? "📈 Bạn đang tiến bộ." : "📉 Cần ôn lại thêm."}
        </div>
      )}

      {hasFinal && comparison.level_changed ? (
        <div style={{ background: "#ecfeff", border: "1px solid #bae6fd", borderRadius: 10, padding: "10px 12px", color: "#0c4a6e", fontWeight: 600 }}>
          🎉 Trình độ của bạn đã nâng lên: {levelLabel(comparison.diagnostic_level)} → {levelLabel(comparison.final_level)}
        </div>
      ) : null}

      {showTopics && hasFinal ? (
        <div style={{ marginTop: 4 }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>So sánh theo từng topic</div>
          {topics.length === 0 ? (
            <div style={{ color: "#64748b" }}>Chưa có dữ liệu theo topic.</div>
          ) : (
            <div style={{ width: "100%", height: 280 }}>
              <ResponsiveContainer>
                <BarChart data={topics} margin={{ top: 8, right: 10, left: 0, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="topic" />
                  <YAxis domain={[0, 100]} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="diagnostic_pct" name="Đầu kỳ" fill="#60a5fa" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="final_pct" name="Cuối kỳ" fill="#1d4ed8" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
