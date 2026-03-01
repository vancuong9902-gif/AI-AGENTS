import { useMemo } from 'react';

function clamp01(x) {
  const n = Number(x);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

export function GroupedBarChart({
  title,
  subtitle,
  categories = [],
  series = [{ key: 'pre', label: 'Đầu vào' }, { key: 'post', label: 'Sau học' }],
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
        const vv = Number(cat?.[s.key] ?? 0) || 0;
        const h = (Math.max(0, Math.min(maxV, vv)) / maxV) * innerH;
        return { key: `${cat.key}-${s.key}`, x: x0 + j * (barW + barGap), y: padding.top + (innerH - h), w: barW, h, label: s.label, value: vv, catLabel: cat.label };
      });
    });
  }, [categories, series, innerW, innerH, padding.left, padding.top, maxV]);

  return (
    <div className='ui-card stack-sm'>
      <div className='row' style={{ justifyContent: 'space-between' }}>
        <div>
          <div className='section-title'>{title}</div>
          {subtitle ? <div className='page-subtitle'>{subtitle}</div> : null}
        </div>
        <div className='row page-subtitle'>
          {series.map((s, idx) => (
            <span key={s.key} className='row'>
              <span style={{ width: 10, height: 10, borderRadius: 999, background: idx === 0 ? 'var(--primary)' : 'var(--muted)' }} />
              {s.label}
            </span>
          ))}
        </div>
      </div>

      <div style={{ overflowX: 'auto', paddingTop: 10 }}>
        <svg width={width} height={height} role='img' aria-label={title}>
          <line x1={padding.left} y1={padding.top} x2={padding.left} y2={padding.top + innerH} stroke='var(--border)' />
          <line x1={padding.left} y1={padding.top + innerH} x2={padding.left + innerW} y2={padding.top + innerH} stroke='var(--border)' />
          {[0, 25, 50, 75, 100].map((t) => {
            const y = padding.top + innerH - (t / 100) * innerH;
            return (
              <g key={t}>
                <line x1={padding.left} y1={y} x2={padding.left + innerW} y2={y} stroke='var(--surface-2)' />
                <text x={padding.left - 10} y={y + 4} textAnchor='end' fontSize='12' fill='var(--muted)'>{t}</text>
              </g>
            );
          })}
          {bars.flat().map((b, idx) => (
            <g key={b.key}>
              <rect x={b.x} y={b.y} width={b.w} height={b.h} rx={8} fill={idx % series.length === 0 ? 'var(--primary)' : 'var(--muted)'} opacity={0.85} />
              <title>{`${b.catLabel} · ${b.label}: ${Math.round(b.value)}`}</title>
            </g>
          ))}
        </svg>
      </div>
    </div>
  );
}

export function HorizontalBarList({ title, items = [], threshold = 0.6 }) {
  const t = clamp01(threshold);
  return (
    <div className='ui-card stack-md'>
      <div className='section-title'>{title}</div>
      {items.map((it) => {
        const v = clamp01(it.value);
        return (
          <div key={it.key} style={{ display: 'grid', gridTemplateColumns: '160px 1fr 56px', gap: 10, alignItems: 'center' }}>
            <div style={{ fontWeight: 700 }}>{it.label}</div>
            <div style={{ position: 'relative', height: 12, background: 'var(--surface-2)', borderRadius: 999 }}>
              <div style={{ width: `${Math.round(v * 100)}%`, height: 12, borderRadius: 999, background: v >= t ? 'var(--primary)' : 'var(--muted)', opacity: 0.9 }} />
              <div style={{ position: 'absolute', left: `${Math.round(t * 100)}%`, top: -4, width: 2, height: 20, background: 'var(--border)' }} title={`Ngưỡng: ${Math.round(t * 100)}%`} />
            </div>
            <div style={{ textAlign: 'right', color: 'var(--muted)', fontVariantNumeric: 'tabular-nums' }}>{Math.round(v * 100)}%</div>
          </div>
        );
      })}
      {items.length === 0 ? <div className='page-subtitle'>Chưa có dữ liệu mức độ thành thạo.</div> : null}
    </div>
  );
}
