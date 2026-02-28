import { useEffect, useMemo, useState } from "react";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { DonutGauge, MetricCard, ProgressBar, Sparkline, pct } from "../components/AnalyticsWidgets";
import StudentLevelBadge from "../components/StudentLevelBadge";
import ProgressComparison from "../components/ProgressComparison";
function num(v, d = 0) {
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  const k = Math.pow(10, d);
  return Math.round(n * k) / k;
}

export default function StudentAnalyticsDashboard() {
  const { role, userId } = useAuth();

  const initialDocId = (() => {
    const qs = new URLSearchParams(window.location.search);
    const q = qs.get("document_id");
    const n = q ? Number(q) : null;
    if (Number.isFinite(n) && n > 0) return n;
    const v = localStorage.getItem("student_analytics_document_id");
    const n2 = v ? Number(v) : null;
    return Number.isFinite(n2) && n2 > 0 ? n2 : null;
  })();

  const [documents, setDocuments] = useState([]);
  const [documentId, setDocumentId] = useState(initialDocId);
  const [windowDays, setWindowDays] = useState(14);
  const [dashboard, setDashboard] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [levelDetails, setLevelDetails] = useState(null);
  const [comparison, setComparison] = useState(null);

  const loadDocs = async () => {
    try {
      const docs = await apiJson("/documents");
      const arr = Array.isArray(docs) ? docs : [];
      setDocuments(arr);
      if (!documentId && arr.length) setDocumentId(Number(arr[0].id));
    } catch {
      // ignore
    }
  };

  const load = async (did = documentId) => {
    setLoading(true);
    setError("");
    try {
      const base = `/analytics/dashboard?user_id=${Number(userId ?? 1)}&window_days=${Number(windowDays)}`;
      const url = did ? `${base}&document_id=${Number(did)}` : base;
      const dash = await apiJson(url);
      setDashboard(dash);

      const histUrl = did
        ? `/analytics/history?user_id=${Number(userId ?? 1)}&document_id=${Number(did)}&limit=120`
        : `/analytics/history?user_id=${Number(userId ?? 1)}&limit=120`;
      const h = await apiJson(histUrl);
      setHistory(Array.isArray(h?.points) ? h.points : []);

      const cid = Number(localStorage.getItem("active_classroom_id"));
      if (Number.isFinite(cid) && cid > 0) {
        const comp = await apiJson(`/v1/students/${Number(userId ?? 1)}/progress?classroomId=${cid}`);
        setComparison(comp || null);
      } else {
        setComparison(null);
      }

      if (did) localStorage.setItem("student_analytics_document_id", String(did));
    } catch (e) {
      setError(e?.message || "Không load được analytics");
      setDashboard(null);
      setHistory([]);
      setComparison(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (role !== "student") return;
    loadDocs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role]);

  useEffect(() => {
    if (role !== "student") return;
    apiJson(`/v1/students/${userId}/level`).then((d) => setLevelDetails(d || null)).catch(() => setLevelDetails(null));
  }, [role, userId]);

  useEffect(() => {
    if (role !== "student") return;
    const base = `/analytics`;
    const url = documentId ? `${base}?document_id=${Number(documentId)}` : base;
    window.history.replaceState({}, "", url);
    load(documentId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId, windowDays]);

  const a = dashboard?.analytics || null;
  const dropout = a?.dropout || {};
  const topicRows = Array.isArray(dashboard?.topics) ? dashboard.topics : [];
  const activity = dashboard?.activity || {};

  const spark = useMemo(() => {
    const pts = (history || []).map((p) => ({ ts: p.ts, value: Number(p.final_score) })).filter((x) => Number.isFinite(x.value));
    return pts;
  }, [history]);

  const docLabel = useMemo(() => {
    const did = documentId ? Number(documentId) : null;
    if (!did) return "(tất cả tài liệu)";
    const d = (documents || []).find((x) => Number(x.id) === did);
    return d ? `#${d.id} • ${d.title}` : `#${did}`;
  }, [documents, documentId]);

  if (role !== "student") {
    return (
      <div style={{ padding: 16 }}>
        <div style={{ background: "#fff3f3", border: "1px solid #ffd0d0", borderRadius: 14, padding: 12 }}>
          Trang này dành cho student.
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1180, margin: "0 auto", padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>📊 My Learning Analytics</h2>
          <div style={{ color: "#666" }}>Theo dõi FinalScore + thành phần + rủi ro dropout (explainable).</div>
          {levelDetails ? (
            <div style={{ marginTop: 8, maxWidth: 360 }}>
              <StudentLevelBadge level={levelDetails} size="md" />
            </div>
          ) : null}
        </div>
        <button onClick={() => load(documentId)} disabled={loading} style={{ padding: "8px 12px" }}>
          Refresh
        </button>
      </div>

      <div style={{ marginTop: 12, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ color: "#666" }}>Document:</span>
        <select value={documentId || ""} onChange={(e) => setDocumentId(e.target.value ? Number(e.target.value) : null)} style={{ padding: 8, borderRadius: 10, border: "1px solid #ddd", minWidth: 320 }}>
          <option value="">-- (tất cả tài liệu) --</option>
          {(documents || []).map((d) => (
            <option key={d.id} value={d.id}>
              #{d.id} • {d.title}
            </option>
          ))}
        </select>

        <span style={{ color: "#666", marginLeft: 8 }}>Window:</span>
        <select value={windowDays} onChange={(e) => setWindowDays(Number(e.target.value))} style={{ padding: 8, borderRadius: 10, border: "1px solid #ddd" }}>
          <option value={7}>7 ngày</option>
          <option value={14}>14 ngày</option>
          <option value={30}>30 ngày</option>
        </select>

        <span style={{ color: "#888", fontSize: 13 }}>Đang xem: {docLabel}</span>
      </div>

      {error ? <div style={{ marginTop: 12, background: "#fff3f3", border: "1px solid #ffd0d0", padding: 12, borderRadius: 12 }}>{error}</div> : null}
      {loading ? <div style={{ marginTop: 12, color: "#666" }}>Đang tải…</div> : null}

      {!loading && comparison && (
        <div style={{ marginTop: 14 }}>
          <div style={{ fontWeight: 900, marginBottom: 8 }}>Tiến bộ tổng thể</div>
          <ProgressComparison comparison={comparison} showTopics />
        </div>
      )}

      {!loading && a && (
        <>
          <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1.2fr 0.8fr", gap: 14, alignItems: "start" }}>
            <MetricCard title="Final Score" value={`${pct(a.final_score) ?? 0}%`} subtitle="Composite score 0–100." right={a.updated_at ? `Updated: ${String(a.updated_at).replace("T", " ").replace("+00:00", "Z")}` : null} />
            <div style={{ background: "#fff", borderRadius: 16, padding: 14, boxShadow: "0 2px 10px rgba(0,0,0,0.06)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline" }}>
                <div style={{ fontWeight: 900 }}>Dropout Risk</div>
                <div style={{ color: "#666", fontSize: 13 }}>{String(dropout.band || "low").toUpperCase()}</div>
              </div>
              <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "140px 1fr", gap: 12, alignItems: "center" }}>
                <DonutGauge value01={dropout.risk} label="risk" />
                <div style={{ display: "grid", gap: 8 }}>
                  {(dropout.drivers || []).slice(0, 3).map((d, idx) => (
                    <div key={idx} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                      <div>
                        <div style={{ fontWeight: 800 }}>{String(d.feature)}</div>
                        <div style={{ color: "#666", fontSize: 12 }}>{String(d.detail || "")}</div>
                      </div>
                      <div style={{ color: "#444", fontVariantNumeric: "tabular-nums" }}>{num(d.contribution, 3)}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, alignItems: "start" }}>
            <div style={{ background: "#fff", borderRadius: 16, padding: 14, boxShadow: "0 2px 10px rgba(0,0,0,0.06)" }}>
              <div style={{ fontWeight: 900 }}>Score components</div>
              <div style={{ marginTop: 12, display: "grid", gap: 12 }}>
                <ProgressBar value01={a.knowledge} labelLeft="Knowledge" labelRight={`${pct(a.knowledge) ?? 0}%`} />
                <ProgressBar value01={a.improvement} labelLeft="Improvement" labelRight={`${pct(a.improvement) ?? 0}%`} />
                <ProgressBar value01={a.engagement} labelLeft="Engagement" labelRight={`${pct(a.engagement) ?? 0}%`} />
                <ProgressBar value01={a.retention} labelLeft="Retention" labelRight={`${pct(a.retention) ?? 0}%`} />
              </div>

              <div style={{ marginTop: 14, borderTop: "1px solid #eee", paddingTop: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline" }}>
                  <div style={{ fontWeight: 900, fontSize: 14 }}>FinalScore trend</div>
                  <div style={{ color: "#666", fontSize: 13 }}>last {spark.length} points</div>
                </div>
                <div style={{ marginTop: 6 }}>
                  <Sparkline points={spark} />
                </div>
              </div>
            </div>

            <div style={{ background: "#fff", borderRadius: 16, padding: 14, boxShadow: "0 2px 10px rgba(0,0,0,0.06)" }}>
              <div style={{ fontWeight: 900 }}>Activity (window)</div>
              <div style={{ marginTop: 10, color: "#666", fontSize: 13 }}>attempts={activity.attempts_count ?? "—"} • quiz_sets={activity.quiz_sets_count ?? "—"} • sessions_days={activity.sessions_days ?? "—"}</div>
              <div style={{ marginTop: 6, color: "#666", fontSize: 13 }}>completion_rate={num(activity.completion_rate, 3) ?? "—"} • time_quality={num(activity.time_quality, 3) ?? "—"} • avg_sec/q={activity.avg_seconds_per_question ?? "—"}</div>

              {documentId ? (
                <div style={{ marginTop: 14, borderTop: "1px solid #eee", paddingTop: 12 }}>
                  <div style={{ fontWeight: 900, fontSize: 14 }}>Topics</div>
                  <div style={{ overflowX: "auto", marginTop: 10 }}>
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead>
                        <tr style={{ textAlign: "left", borderBottom: "1px solid #eee" }}>
                          <th style={{ padding: "8px 6px" }}>#</th>
                          <th style={{ padding: "8px 6px" }}>Topic</th>
                          <th style={{ padding: "8px 6px" }}>Mastery</th>
                          <th style={{ padding: "8px 6px" }}>Retention due</th>
                        </tr>
                      </thead>
                      <tbody>
                        {topicRows.slice(0, 10).map((r) => (
                          <tr key={r.topic_id} style={{ borderBottom: "1px solid #f2f2f2" }}>
                            <td style={{ padding: "8px 6px", color: "#666" }}>{r.topic_index}</td>
                            <td style={{ padding: "8px 6px", fontWeight: 700 }}>{r.title}</td>
                            <td style={{ padding: "8px 6px" }}>{pct(r.mastery) ?? 0}%</td>
                            <td style={{ padding: "8px 6px" }}>{r.retention_due_count ?? 0}</td>
                          </tr>
                        ))}
                        {topicRows.length === 0 ? (
                          <tr>
                            <td colSpan={4} style={{ padding: 10, color: "#666" }}>Chưa có topics cho document này.</td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
