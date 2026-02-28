import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { DonutGauge, MetricCard, ProgressBar, Sparkline, pct } from "../components/AnalyticsWidgets";

function bandTone(band) {
  if (band === "high") return "danger";
  if (band === "medium") return "warn";
  return "neutral";
}

function fmtBand(band) {
  if (band === "high") return "HIGH";
  if (band === "medium") return "MEDIUM";
  return "LOW";
}

function num(v, d = 0) {
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  const k = Math.pow(10, d);
  return Math.round(n * k) / k;
}

export default function TeacherAnalyticsDashboard() {
  const { role, userId } = useAuth();
  const params = useParams();
  const navigate = useNavigate();

  const initialStudentId = (() => {
    const raw = params.studentId ?? localStorage.getItem("teacher_analytics_student_id") ?? 1;
    const n = Number(raw);
    return Number.isFinite(n) && n > 0 ? n : 1;
  })();

  const initialDocId = (() => {
    const qs = new URLSearchParams(window.location.search);
    const q = qs.get("document_id");
    const n = q ? Number(q) : null;
    if (Number.isFinite(n) && n > 0) return n;
    const v = localStorage.getItem("teacher_analytics_document_id");
    const n2 = v ? Number(v) : null;
    return Number.isFinite(n2) && n2 > 0 ? n2 : null;
  })();

  const [studentId, setStudentId] = useState(initialStudentId);
  const [studentInput, setStudentInput] = useState(String(initialStudentId));
  const [classId] = useState(() => {
    const v = localStorage.getItem("teacher_active_classroom_id");
    const n = v ? Number(v) : null;
    return Number.isFinite(n) && n > 0 ? n : null;
  });
  const [documents, setDocuments] = useState([]);
  const [documentId, setDocumentId] = useState(initialDocId);
  const [windowDays, setWindowDays] = useState(14);

  const [dashboard, setDashboard] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [weights, setWeights] = useState({ w1: 0.45, w2: 0.25, w3: 0.15, w4: 0.15 });
  const [savingW, setSavingW] = useState(false);
  const [classroomInput, setClassroomInput] = useState(localStorage.getItem("teacher_report_classroom_id") || "1");
  const [reportToast, setReportToast] = useState("");
  const [latestReport, setLatestReport] = useState(null);

  const loadDocs = async () => {
    try {
      const docs = await apiJson("/documents");
      const arr = Array.isArray(docs) ? docs : [];
      setDocuments(arr);
      if (!documentId && arr.length) {
        setDocumentId(Number(arr[0].id));
      }
    } catch {
      // ignore
    }
  };

  const load = async (sid = studentId, did = documentId) => {
    setLoading(true);
    setError("");
    try {
      const base = `/analytics/dashboard?user_id=${Number(sid)}&window_days=${Number(windowDays)}`;
      const url = did ? `${base}&document_id=${Number(did)}` : base;
      const dash = await apiJson(url);
      setDashboard(dash);

      const histUrl = did
        ? `/analytics/history?user_id=${Number(sid)}&document_id=${Number(did)}&limit=120`
        : `/analytics/history?user_id=${Number(sid)}&limit=120`;
      const h = await apiJson(histUrl);
      setHistory(Array.isArray(h?.points) ? h.points : []);

      const w = dash?.analytics?.weights;
      if (w && typeof w === "object") {
        setWeights({
          w1: Number(w.w1_knowledge ?? 0.45),
          w2: Number(w.w2_improvement ?? 0.25),
          w3: Number(w.w3_engagement ?? 0.15),
          w4: Number(w.w4_retention ?? 0.15),
        });
      }
    } catch (e) {
      setError(e?.message || "Không load được analytics");
      setDashboard(null);
      setHistory([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (role !== "teacher") return;
    loadDocs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role]);

  useEffect(() => {
    if (role !== "teacher") return;
    localStorage.setItem("teacher_analytics_student_id", String(studentId));
    if (documentId) localStorage.setItem("teacher_analytics_document_id", String(documentId));

    const base = `/teacher/analytics/${Number(studentId)}`;
    const url = documentId ? `${base}?document_id=${Number(documentId)}` : base;
    window.history.replaceState({}, "", url);
    load(studentId, documentId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studentId, documentId, windowDays]);



  useEffect(() => {
    if (role !== "teacher") return undefined;
    pollLatestClassReport();
    const timer = setInterval(() => {
      pollLatestClassReport();
    }, 30000);
    return () => clearInterval(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role, classroomInput]);

  const applyStudent = () => {
    const n = Number(studentInput);
    if (!Number.isFinite(n) || n <= 0) return;
    setStudentId(n);
    navigate(`/teacher/analytics/${n}${documentId ? `?document_id=${Number(documentId)}` : ""}`);
  };



  const pollLatestClassReport = async () => {
    const cid = Number(classroomInput);
    if (!Number.isFinite(cid) || cid <= 0) return;
    try {
      localStorage.setItem("teacher_report_classroom_id", String(cid));
      const rep = await apiJson(`/classrooms/${cid}/reports/latest`);
      if (!rep?.id) return;
      setLatestReport(rep);
      const seen = Number(localStorage.getItem("teacher_latest_report_seen") || 0);
      if (Number(rep.id) > seen) {
        setReportToast("📊 Báo cáo cuối kỳ đã sẵn sàng!");
        localStorage.setItem("teacher_latest_report_seen", String(rep.id));
      }
    } catch {
      // ignore polling errors
    }
  const openReportExport = (format) => {
    if (!classId) return;
    window.open(`/api/classrooms/${classId}/reports/latest/export?format=${format}`, "_blank");
  };

  const saveWeights = async () => {
    setSavingW(true);
    try {
      await apiJson("/analytics/weights", {
        method: "POST",
        body: {
          user_id: studentId,
          w1_knowledge: Number(weights.w1),
          w2_improvement: Number(weights.w2),
          w3_engagement: Number(weights.w3),
          w4_retention: Number(weights.w4),
        },
      });
      await load(studentId, documentId);
    } catch (e) {
      setError(e?.message || "Không lưu được weights");
    } finally {
      setSavingW(false);
    }
  };

  const a = dashboard?.analytics || null;
  const dropout = a?.dropout || {};
  const band = dropout?.band || "low";

  const spark = useMemo(() => {
    const pts = (history || []).map((p) => ({
      ts: p.ts,
      value: Number(p.final_score),
    })).filter((x) => Number.isFinite(x.value));
    return pts;
  }, [history]);

  const topicRows = Array.isArray(dashboard?.topics) ? dashboard.topics : [];
  const activity = dashboard?.activity || {};

  const docLabel = useMemo(() => {
    const did = documentId ? Number(documentId) : null;
    if (!did) return "(tất cả tài liệu)";
    const d = (documents || []).find((x) => Number(x.id) === did);
    return d ? `#${d.id} • ${d.title}` : `#${did}`;
  }, [documents, documentId]);

  if (role !== "teacher") {
    return (
      <div style={{ padding: 16 }}>
        <div style={{ background: "#fff3f3", border: "1px solid #ffd0d0", borderRadius: 14, padding: 12 }}>
          Trang này dành cho teacher.
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1180, margin: "0 auto", padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>📊 Composite Analytics Dashboard</h2>
          <div style={{ color: "#666" }}>FinalScore = w1·Knowledge + w2·Improvement + w3·Engagement + w4·Retention + Dropout risk.</div>
        </div>
        <button onClick={() => load(studentId, documentId)} disabled={loading} style={{ padding: "8px 12px" }}>
          Refresh
        </button>
      </div>

      <div style={{ marginTop: 12, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ color: "#666" }}>Student ID:</span>
        <input value={studentInput} onChange={(e) => setStudentInput(e.target.value)} style={{ width: 120, padding: 8, borderRadius: 10, border: "1px solid #ddd" }} />
        <button onClick={applyStudent} disabled={loading} style={{ padding: "8px 12px" }}>
          Xem
        </button>

        <span style={{ color: "#666", marginLeft: 8 }}>Document:</span>
        <select value={documentId || ""} onChange={(e) => setDocumentId(e.target.value ? Number(e.target.value) : null)} style={{ padding: 8, borderRadius: 10, border: "1px solid #ddd", minWidth: 320 }}>
          <option value="">-- (tất cả tài liệu) --</option>
          {(documents || []).map((d) => (
            <option key={d.id} value={d.id}>
              #{d.id} • {d.title}
            </option>
          ))}
        </select>

        <span style={{ color: "#666", marginLeft: 8 }}>Classroom ID (report):</span>
        <input value={classroomInput} onChange={(e) => setClassroomInput(e.target.value)} style={{ width: 120, padding: 8, borderRadius: 10, border: "1px solid #ddd" }} />

        <span style={{ color: "#666", marginLeft: 8 }}>Window:</span>
        <select value={windowDays} onChange={(e) => setWindowDays(Number(e.target.value))} style={{ padding: 8, borderRadius: 10, border: "1px solid #ddd" }}>
          <option value={7}>7 ngày</option>
          <option value={14}>14 ngày</option>
          <option value={30}>30 ngày</option>
        </select>

        <span style={{ color: "#888", fontSize: 13 }}>Đang xem: {docLabel} • Teacher ID: {userId ?? 1}</span>

        <button onClick={() => openReportExport("pdf")} disabled={!classId} style={{ padding: "8px 12px" }}>
          📥 Xuất báo cáo PDF
        </button>
        <button onClick={() => openReportExport("docx")} disabled={!classId} style={{ padding: "8px 12px" }}>
          📝 Xuất Word
        </button>
      </div>

      {reportToast ? (
        <div style={{ marginTop: 12, background: "#ecfeff", border: "1px solid #a5f3fc", padding: 12, borderRadius: 12, display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
          <span>{reportToast}</span>
          {latestReport?.id ? (
            <button onClick={() => navigate(`/teacher/classrooms/${Number(classroomInput)}/reports/${latestReport.id}`)} style={{ padding: "6px 10px" }}>
              Xem chi tiết
            </button>
          ) : null}
        </div>
      ) : null}

      {error ? <div style={{ marginTop: 12, background: "#fff3f3", border: "1px solid #ffd0d0", padding: 12, borderRadius: 12 }}>{error}</div> : null}
      {loading ? <div style={{ marginTop: 12, color: "#666" }}>Đang tải…</div> : null}

      {!loading && a && (
        <>
          <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1.2fr 0.8fr", gap: 14, alignItems: "start" }}>
            <MetricCard
              title="Final Score"
              value={`${pct(a.final_score) ?? 0}%`}
              subtitle="Composite score (0–100). Được tính từ Knowledge/Improvement/Engagement/Retention theo weights."
              right={a.updated_at ? `Updated: ${String(a.updated_at).replace("T", " ").replace("+00:00", "Z")}` : null}
            />

            <MetricCard
              title="Dropout Risk"
              tone={bandTone(band)}
              value={`${pct(dropout.risk) ?? 0}%`}
              subtitle={`Risk band: ${fmtBand(band)}. Drivers hiển thị phía dưới (explainable logistic model).`}
              right={documentId ? "Doc-scoped" : "Global"}
            />
          </div>

          <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, alignItems: "start" }}>
            <div style={{ background: "#fff", borderRadius: 16, padding: 14, boxShadow: "0 2px 10px rgba(0,0,0,0.06)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "baseline" }}>
                <div style={{ fontWeight: 900 }}>Score Decomposition</div>
                <div style={{ color: "#666", fontSize: 13 }}>weights editable</div>
              </div>

              <div style={{ marginTop: 12, display: "grid", gap: 12 }}>
                <ProgressBar value01={a.knowledge} labelLeft={`Knowledge (w1=${num(weights.w1, 2)})`} labelRight={`${pct(a.knowledge) ?? 0}%`} />
                <ProgressBar value01={a.improvement} labelLeft={`Improvement (w2=${num(weights.w2, 2)})`} labelRight={`${pct(a.improvement) ?? 0}%`} />
                <ProgressBar value01={a.engagement} labelLeft={`Engagement (w3=${num(weights.w3, 2)})`} labelRight={`${pct(a.engagement) ?? 0}%`} />
                <ProgressBar value01={a.retention} labelLeft={`Retention (w4=${num(weights.w4, 2)})`} labelRight={`${pct(a.retention) ?? 0}%`} />
              </div>

              <div style={{ marginTop: 14, borderTop: "1px solid #eee", paddingTop: 12, display: "grid", gap: 10 }}>
                <div style={{ fontWeight: 900, fontSize: 14 }}>Set Weights</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <label style={{ display: "grid", gap: 6, color: "#666", fontSize: 13 }}>
                    w1 Knowledge
                    <input type="number" step="0.01" value={weights.w1} onChange={(e) => setWeights((s) => ({ ...s, w1: e.target.value }))} style={{ padding: 8, borderRadius: 10, border: "1px solid #ddd" }} />
                  </label>
                  <label style={{ display: "grid", gap: 6, color: "#666", fontSize: 13 }}>
                    w2 Improvement
                    <input type="number" step="0.01" value={weights.w2} onChange={(e) => setWeights((s) => ({ ...s, w2: e.target.value }))} style={{ padding: 8, borderRadius: 10, border: "1px solid #ddd" }} />
                  </label>
                  <label style={{ display: "grid", gap: 6, color: "#666", fontSize: 13 }}>
                    w3 Engagement
                    <input type="number" step="0.01" value={weights.w3} onChange={(e) => setWeights((s) => ({ ...s, w3: e.target.value }))} style={{ padding: 8, borderRadius: 10, border: "1px solid #ddd" }} />
                  </label>
                  <label style={{ display: "grid", gap: 6, color: "#666", fontSize: 13 }}>
                    w4 Retention
                    <input type="number" step="0.01" value={weights.w4} onChange={(e) => setWeights((s) => ({ ...s, w4: e.target.value }))} style={{ padding: 8, borderRadius: 10, border: "1px solid #ddd" }} />
                  </label>
                </div>
                <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  <button onClick={saveWeights} disabled={savingW || loading} style={{ padding: "8px 12px" }}>
                    {savingW ? "Saving…" : "Save weights"}
                  </button>
                  <div style={{ color: "#666", fontSize: 13 }}>Backend sẽ normalize nếu tổng weights ≠ 1.</div>
                </div>
              </div>
            </div>

            <div style={{ background: "#fff", borderRadius: 16, padding: 14, boxShadow: "0 2px 10px rgba(0,0,0,0.06)" }}>
              <div style={{ fontWeight: 900 }}>Risk & Trend</div>

              <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "140px 1fr", gap: 12, alignItems: "center" }}>
                <DonutGauge value01={dropout.risk} label="Dropout" />
                <div>
                  <div style={{ fontWeight: 900, fontSize: 14 }}>Top Drivers</div>
                  <div style={{ marginTop: 8, display: "grid", gap: 8 }}>
                    {(dropout.drivers || []).map((d, idx) => (
                      <div key={idx} style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline" }}>
                        <div>
                          <div style={{ fontWeight: 800 }}>{String(d.feature)}</div>
                          <div style={{ color: "#666", fontSize: 12 }}>{String(d.detail || "")}</div>
                        </div>
                        <div style={{ fontVariantNumeric: "tabular-nums", color: "#444" }}>{num(d.contribution, 3)}</div>
                      </div>
                    ))}
                    {(!dropout.drivers || dropout.drivers.length === 0) ? <div style={{ color: "#666" }}>—</div> : null}
                  </div>
                </div>
              </div>

              <div style={{ marginTop: 14, borderTop: "1px solid #eee", paddingTop: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline" }}>
                  <div style={{ fontWeight: 900, fontSize: 14 }}>FinalScore trend</div>
                  <div style={{ color: "#666", fontSize: 13 }}>last {spark.length} points</div>
                </div>
                <div style={{ marginTop: 6 }}>
                  <Sparkline points={spark.map((p) => ({ ...p, value: p.value }))} />
                </div>
              </div>

              <div style={{ marginTop: 14, borderTop: "1px solid #eee", paddingTop: 12, display: "grid", gap: 8 }}>
                <div style={{ fontWeight: 900, fontSize: 14 }}>Activity (window)</div>
                <div style={{ color: "#666", fontSize: 13 }}>attempts={activity.attempts_count ?? "—"} • quiz_sets={activity.quiz_sets_count ?? "—"} • sessions_days={activity.sessions_days ?? "—"}</div>
                <div style={{ color: "#666", fontSize: 13 }}>completion_rate={num(activity.completion_rate, 3) ?? "—"} • time_quality={num(activity.time_quality, 3) ?? "—"} • avg_sec/q={activity.avg_seconds_per_question ?? "—"}</div>
              </div>
            </div>
          </div>

          {documentId ? (
            <div style={{ marginTop: 14, background: "#fff", borderRadius: 16, padding: 14, boxShadow: "0 2px 10px rgba(0,0,0,0.06)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline" }}>
                <div style={{ fontWeight: 900 }}>Topic Metrics</div>
                <div style={{ color: "#666", fontSize: 13 }}>mastery • retention due • half-life • next step</div>
              </div>
              <div style={{ overflowX: "auto", marginTop: 10 }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ textAlign: "left", borderBottom: "1px solid #eee" }}>
                      <th style={{ padding: "8px 6px" }}>#</th>
                      <th style={{ padding: "8px 6px" }}>Topic</th>
                      <th style={{ padding: "8px 6px" }}>Mastery</th>
                      <th style={{ padding: "8px 6px" }}>Last score</th>
                      <th style={{ padding: "8px 6px" }}>Next</th>
                      <th style={{ padding: "8px 6px" }}>Retention due</th>
                      <th style={{ padding: "8px 6px" }}>Half-life (d)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topicRows.map((r) => (
                      <tr key={r.topic_id} style={{ borderBottom: "1px solid #f2f2f2" }}>
                        <td style={{ padding: "8px 6px", color: "#666", fontVariantNumeric: "tabular-nums" }}>{r.topic_index}</td>
                        <td style={{ padding: "8px 6px", fontWeight: 700 }}>{r.title}</td>
                        <td style={{ padding: "8px 6px", fontVariantNumeric: "tabular-nums" }}>{pct(r.mastery) ?? 0}%</td>
                        <td style={{ padding: "8px 6px", fontVariantNumeric: "tabular-nums" }}>{r.last_score_percent ?? "—"}</td>
                        <td style={{ padding: "8px 6px", color: "#666" }}>{r.next_step ? `${r.next_step} (${r.next_difficulty || ""})` : "—"}</td>
                        <td style={{ padding: "8px 6px", fontVariantNumeric: "tabular-nums" }}>{r.retention_due_count ?? 0}</td>
                        <td style={{ padding: "8px 6px", fontVariantNumeric: "tabular-nums" }}>{r.half_life_days ?? "—"}</td>
                      </tr>
                    ))}
                    {topicRows.length === 0 ? (
                      <tr>
                        <td colSpan={7} style={{ padding: 10, color: "#666" }}>
                          Chưa có topics cho document này (hãy chạy Phase 1 hoặc upload tài liệu).
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
