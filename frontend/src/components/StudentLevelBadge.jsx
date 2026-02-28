const COLOR_THEME = {
  green: { bg: "#f6ffed", border: "#b7eb8f", text: "#237804" },
  blue: { bg: "#e6f4ff", border: "#91caff", text: "#0958d9" },
  orange: { bg: "#fff7e6", border: "#ffd591", text: "#ad6800" },
  red: { bg: "#fff1f0", border: "#ffa39e", text: "#a8071a" },
};

function toLevel(level) {
  if (!level || typeof level !== "object") return null;
  const color = COLOR_THEME[level.color] ? level.color : "blue";
  return {
    emoji: level.emoji || "⭐",
    label: level.label || "Khá",
    description: level.description || "",
    learningApproach: level.learning_approach || "",
    color,
  };
}

export default function StudentLevelBadge({ level, showDescription = true, size = "md" }) {
  const data = toLevel(level);
  if (!data) return null;
  const theme = COLOR_THEME[data.color];

  if (size === "sm") {
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 10px", borderRadius: 999, background: theme.bg, border: `1px solid ${theme.border}`, color: theme.text, fontWeight: 700 }}>
        <span>{data.emoji}</span>
        <span>{data.label}</span>
      </span>
    );
  }

  if (size === "md") {
    return (
      <div style={{ border: `1px solid ${theme.border}`, background: theme.bg, borderRadius: 12, padding: 12, color: theme.text }}>
        <div style={{ fontWeight: 800 }}>{data.emoji} {data.label}</div>
        {showDescription && <div style={{ marginTop: 4, color: "#334155", fontSize: 14 }}>{data.description}</div>}
      </div>
    );
  }

  return (
    <div style={{ border: `1px solid ${theme.border}`, background: theme.bg, borderRadius: 14, padding: 14 }}>
      <div style={{ fontWeight: 900, color: theme.text, fontSize: 18 }}>{data.emoji} Trình độ của bạn: {String(data.label).toUpperCase()}</div>
      {showDescription && <div style={{ marginTop: 6, color: "#334155" }}>&quot;{data.description}&quot;</div>}
      <div style={{ marginTop: 8, color: "#0f172a" }}><strong>Cách học AI gợi ý:</strong> {data.learningApproach}</div>
    </div>
  );
}
