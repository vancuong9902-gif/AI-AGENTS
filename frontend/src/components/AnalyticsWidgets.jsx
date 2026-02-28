import { useMemo } from "react";

export function pct(x, digits = 0) {
  const n = Number(x);
  if (!Number.isFinite(n)) return null;
  return Math.round(n * 100 * Math.pow(10, digits)) / Math.pow(10, digits);
}

function clamp01(x) {
  const n = Number(x);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

export function MetricCard({ title, value, subtitle, right, tone = "neutral" }) {
  const bg = tone === "danger" ? "#fff3f3" : tone === "warn" ? "#fff8e6" : "#fff";
  const border = tone === "danger" ? "#ffd0d0" : tone === "warn" ? "#ffe1a3" : "#eee";

  return (
    <div style={{ background: bg, border: `1px solid ${border}`, borderRadius: 16, padding: 14, boxShadow: "0 2px 10px rgba(0,0,0,0.05)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline" }}>
        <div style={{ fontWeight: 900 }}>{title}</div>
        {right ? <div style={{ color: "#666", fontSize: 13 }}>{right}</div> : null}
      </div>
      <div style={{ marginTop: 10, fontSize: 28, fontWeight: 950, letterSpacing: -0.3, fontVariantNumeric: "tabular-nums" }}>
        {value}
      </div>
      {subtitle ? <div style={{ marginTop: 6, color: "#666", lineHeight: 1.35 }}>{subtitle}</div> : null}
    </div>
  );
}

export function ProgressBar({ value01, labelLeft, labelRight }) {
  const v = clamp01(value01);
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, color: "#666", fontSize: 13 }}>
        <span>{labelLeft}</span>
        <span style={{ fontVariantNumeric: "tabular-nums" }}>{labelRight}</span>
      </div>
      <div style={{ height: 10, background: "#f2f2f2", borderRadius: 999, marginTop: 6, overflow: "hidden" }}>
        <div style={{ width: `${Math.round(v * 100)}%`, height: 10, background: "#111", opacity: 0.9 }} />
      </div>
    </div>
  );
}

export function DonutGauge({ value01, size = 120, label }) {
  const v = clamp01(value01);
  const r = (size / 2) - 10;
  const c = 2 * Math.PI * r;
  const dash = c * v;
  const gap = c - dash;

  return (
    <div style={{ display: "grid", placeItems: "center" }}>
      <svg width={size} height={size} role="img" aria-label={label || "gauge"}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#eee" strokeWidth="10" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="#111"
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${gap}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text x="50%" y="50%" textAnchor="middle" dominantBaseline="middle" fontSize="22" fontWeight="900" fill="#111">
          {Math.round(v * 100)}%
        </text>
      </svg>
      {label ? <div style={{ marginTop: -2, color: "#666", fontSize: 13 }}>{label}</div> : null}
    </div>
  );
}

export function Sparkline({ points = [], height = 54 }) {
  // points: [{ts, value}] with value in [0,1]
  const { path, minV, maxV } = useMemo(() => {
    const vals = (points || []).map((p) => Number(p.value)).filter((x) => Number.isFinite(x));
    if (!vals.length) return { path: "", minV: 0, maxV: 1 };
    const mn = Math.min(...vals);
    const mx = Math.max(...vals);
    const minV2 = Number.isFinite(mn) ? mn : 0;
    const maxV2 = Number.isFinite(mx) ? mx : 1;
    return { path: "", minV: minV2, maxV: maxV2 };
  }, [points]);

  const w = 220;
  const pad = 6;
  const innerW = w - pad * 2;
  const innerH = height - pad * 2;
  const vals = (points || []).map((p) => clamp01(p.value));
  if (!vals.length) {
    return <div style={{ height, color: "#999", display: "grid", alignItems: "center" }}>—</div>;
  }
  const mn = Math.min(...vals);
  const mx = Math.max(...vals);
  const denom = Math.max(1e-6, mx - mn);
  const pts = vals.map((v, i) => {
    const x = pad + (i / Math.max(1, vals.length - 1)) * innerW;
    const y = pad + (1 - ((v - mn) / denom)) * innerH;
    return { x, y };
  });
  const d = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ");

  return (
    <svg width={w} height={height} role="img" aria-label="sparkline">
      <path d={d} fill="none" stroke="#111" strokeWidth="2" opacity="0.9" />
    </svg>
  );
}
