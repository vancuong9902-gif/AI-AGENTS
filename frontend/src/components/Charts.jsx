import { useMemo } from "react";

// Lightweight SVG charts (no external deps) for the demo.

function clamp01(x) {
  const n = Number(x);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

export function GroupedBarChart({
  title,
  subtitle,
  categories = [],
  series = [
    { key: "pre", label: "Pre" },
    { key: "post", label: "Post" },
  ],
  height = 260,
  maxValue = 100,
}) {
  const width = 760;
  const padding = { top: 28, right: 18, bottom: 46, left: 44 };
  const innerW = width - padding.left - padding.right;
  const innerH = height - padding.top - padding.bottom;

  const maxV = Number.isFinite(Number(maxValue)) ? Number(maxValue) : 100;

  const bars = useMemo(() => {
    const groupCount = Math.max(1, categories.length);
    const groupGap = 22;
    const groupW = (innerW - groupGap * (groupCount - 1)) / groupCount;
    const barGap = 8;
    const barW = (groupW - barGap * (series.length - 1)) / series.length;

    return categories.map((cat, i) => {
      const x0 = padding.left + i * (groupW + groupGap);
      return series.map((s, j) => {
        const v = Number(cat?.[s.key] ?? 0);
        const vv = Number.isFinite(v) ? v : 0;
        const h = (Math.max(0, Math.min(maxV, vv)) / maxV) * innerH;
        const x = x0 + j * (barW + barGap);
        const y = padding.top + (innerH - h);
        return {
          key: `${cat.key}-${s.key}`,
          x,
          y,
          w: barW,
          h,
          label: s.label,
          value: vv,
          catLabel: cat.label,
        };
      });
    });
  }, [categories, series, innerW, innerH, padding.left, padding.top, maxV]);

  // Y ticks
  const ticks = [0, 25, 50, 75, 100];

  return (
    <div
      style={{
        background: "#fff",
        borderRadius: 16,
        padding: 14,
        boxShadow: "0 2px 10px rgba(0,0,0,0.06)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline" }}>
        <div>
          <div style={{ fontWeight: 800, fontSize: 16 }}>{title}</div>
          {subtitle ? <div style={{ color: "#666", marginTop: 4 }}>{subtitle}</div> : null}
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", color: "#555" }}>
          {series.map((s, idx) => (
            <div key={s.key} style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: 999,
                  background: idx === 0 ? "#111" : "#999",
                  display: "inline-block",
                }}
              />
              <span style={{ fontSize: 13 }}>{s.label}</span>
            </div>
          ))}
        </div>
      </div>

      <div style={{ overflowX: "auto", paddingTop: 10 }}>
        <svg width={width} height={height} role="img" aria-label={title}>
          {/* Axes */}
          <line
            x1={padding.left}
            y1={padding.top}
            x2={padding.left}
            y2={padding.top + innerH}
            stroke="#ddd"
          />
          <line
            x1={padding.left}
            y1={padding.top + innerH}
            x2={padding.left + innerW}
            y2={padding.top + innerH}
            stroke="#ddd"
          />

          {ticks.map((t) => {
            const y = padding.top + innerH - (t / 100) * innerH;
            return (
              <g key={t}>
                <line x1={padding.left} y1={y} x2={padding.left + innerW} y2={y} stroke="#f2f2f2" />
                <text x={padding.left - 10} y={y + 4} textAnchor="end" fontSize="12" fill="#777">
                  {t}
                </text>
              </g>
            );
          })}

          {/* Bars */}
          {bars.flat().map((b, idx) => (
            <g key={b.key}>
              <rect
                x={b.x}
                y={b.y}
                width={b.w}
                height={b.h}
                rx={8}
                fill={idx % series.length === 0 ? "#111" : "#999"}
                opacity={0.9}
              />
              <title>
                {b.catLabel} · {b.label}: {Math.round(b.value)}
              </title>
            </g>
          ))}

          {/* X labels */}
          {categories.map((cat, i) => {
            const groupCount = Math.max(1, categories.length);
            const groupGap = 22;
            const groupW = (innerW - groupGap * (groupCount - 1)) / groupCount;
            const x = padding.left + i * (groupW + groupGap) + groupW / 2;
            const y = padding.top + innerH + 28;
            return (
              <text
                key={cat.key}
                x={x}
                y={y}
                textAnchor="middle"
                fontSize="12"
                fill="#444"
              >
                {cat.label}
              </text>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

export function HorizontalBarList({ title, items = [], threshold = 0.6 }) {
  const t = clamp01(threshold);
  return (
    <div
      style={{
        background: "#fff",
        borderRadius: 16,
        padding: 14,
        boxShadow: "0 2px 10px rgba(0,0,0,0.06)",
      }}
    >
      <div style={{ fontWeight: 800, fontSize: 16 }}>{title}</div>
      <div style={{ marginTop: 12, display: "grid", gap: 10 }}>
        {items.map((it) => {
          const v = clamp01(it.value);
          return (
            <div key={it.key} style={{ display: "grid", gridTemplateColumns: "160px 1fr 56px", gap: 10, alignItems: "center" }}>
              <div style={{ fontWeight: 700, color: "#222" }}>{it.label}</div>
              <div style={{ position: "relative", height: 12, background: "#f2f2f2", borderRadius: 999 }}>
                <div
                  style={{
                    width: `${Math.round(v * 100)}%`,
                    height: 12,
                    borderRadius: 999,
                    background: v >= t ? "#111" : "#999",
                    opacity: 0.9,
                  }}
                />
                <div
                  style={{
                    position: "absolute",
                    left: `${Math.round(t * 100)}%`,
                    top: -4,
                    width: 2,
                    height: 20,
                    background: "#e0e0e0",
                  }}
                  title={`Ngưỡng: ${Math.round(t * 100)}%`}
                />
              </div>
              <div style={{ textAlign: "right", color: "#444", fontVariantNumeric: "tabular-nums" }}>
                {Math.round(v * 100)}%
              </div>
            </div>
          );
        })}

        {items.length === 0 && <div style={{ color: "#666" }}>Chưa có dữ liệu mastery.</div>}
      </div>
    </div>
  );
}
