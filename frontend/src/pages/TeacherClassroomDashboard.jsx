import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiJson } from "../lib/api";
import { GroupedBarChart, HorizontalBarList } from "../components/Charts";
import { FaArrowLeft, FaChartLine, FaClipboard, FaFilter, FaPaperPlane, FaSearch, FaSyncAlt, FaUsers } from "react-icons/fa";

function Card({ children, style }) {
  return (
    <div
      style={{
        background: "#fff",
        borderRadius: 18,
        padding: 16,
        boxShadow: "0 2px 16px rgba(0,0,0,0.06)",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

function StatCard({ title, value, hint }) {
  return (
    <Card style={{ padding: 14 }}>
      <div style={{ color: "#666", fontWeight: 900, fontSize: 12 }}>{title}</div>
      <div style={{ fontSize: 26, fontWeight: 1000, marginTop: 6 }}>{value}</div>
      {hint ? <div style={{ marginTop: 6, color: "#666" }}>{hint}</div> : null}
    </Card>
  );
}

function ProgressPill({ pct }) {
  const p = Math.max(0, Math.min(100, Number(pct) || 0));
  const good = p >= 70;
  return (
    <span
      style={{
        padding: "6px 10px",
        borderRadius: 999,
        border: "1px solid #eee",
        background: good ? "#f6fff6" : "#fff7f0",
        color: "#222",
        fontWeight: 1000,
        fontVariantNumeric: "tabular-nums",
      }}
      title="Progress"
    >
      {Math.round(p)}%
    </span>
  );
}



function AINarrativeCard({ narrative }) {
  if (!narrative) return null;
  return (
    <div
      style={{
        background: "linear-gradient(135deg, #e3f2fd, #bbdefb)",
        border: "1px solid #2196F3",
        borderRadius: 12,
        padding: "16px 20px",
        marginBottom: 20,
      }}
    >
      <div style={{ fontWeight: 700, color: "#1565C0", marginBottom: 8, fontSize: 15 }}>🤖 Nhận xét từ AI</div>
      <p style={{ margin: 0, color: "#333", lineHeight: 1.7, fontSize: 14 }}>{narrative}</p>
    </div>
  );
}

function ProgressChart({ data }) {
  if (!data?.length) return null;
  const categories = data.map((item) => ({
    key: String(item.student_id),
    label: `#${item.student_id}`,
    pre: Number(item.pre_score) || 0,
    post: Number(item.post_score) || 0,
  }));
  return (
    <GroupedBarChart
      title="📈 Tiến bộ: Điểm đầu vào vs Cuối kỳ"
      subtitle="So sánh điểm pre-test và post-test theo từng học sinh"
      categories={categories}
      series={[
        { key: "pre", label: "Điểm đầu vào" },
        { key: "post", label: "Điểm cuối kỳ" },
      ]}
      maxValue={100}
      height={300}
    />
  );
}

function WeakTopicsTable({ topics }) {
  if (!topics || topics.length === 0) return null;
  return (
    <div style={{ background: "#fff", borderRadius: 12, padding: 16, marginBottom: 20, boxShadow: "0 2px 16px rgba(0,0,0,0.06)" }}>
      <h3 style={{ marginTop: 0, color: "#C62828" }}>⚠️ Các phần học sinh đang yếu nhất</h3>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ background: "#FEE2E2" }}>
            <th style={{ padding: "8px 12px", textAlign: "left" }}>Chủ đề</th>
            <th style={{ padding: "8px 12px", textAlign: "center" }}>Điểm TB</th>
            <th style={{ padding: "8px 12px", textAlign: "center" }}>Học sinh yếu</th>
            <th style={{ padding: "8px 12px", textAlign: "left" }}>Đề xuất</th>
          </tr>
        </thead>
        <tbody>
          {topics.slice(0, 5).map((t, i) => (
            <tr key={`${t.topic}-${i}`} style={{ borderBottom: "1px solid #eee", background: i % 2 === 0 ? "#fff" : "#FFF7ED" }}>
              <td style={{ padding: "8px 12px", fontWeight: 600 }}>{t.topic}</td>
              <td style={{ padding: "8px 12px", textAlign: "center", color: t.avg_pct < 50 ? "#DC2626" : "#D97706" }}>{t.avg_pct}%</td>
              <td style={{ padding: "8px 12px", textAlign: "center" }}>
                {t.weak_count}/{t.total}
              </td>
              <td style={{ padding: "8px 12px", color: "#555", fontSize: 12 }}>{t.suggestion}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function clamp(x, a, b) {
  const n = Number(x);
  if (!Number.isFinite(n)) return a;
  return Math.max(a, Math.min(b, n));
}

export default function TeacherClassroomDashboard() {
  const { id } = useParams();
  const classroomId = Number(id);

  const [data, setData] = useState(null);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  // Filters
  const [query, setQuery] = useState("");
  const [minProgress, setMinProgress] = useState(0);
  const [minHomework, setMinHomework] = useState(0);
  const [needHelpOnly, setNeedHelpOnly] = useState(false);
  const [needHelpThreshold, setNeedHelpThreshold] = useState(60);
  const [sortKey, setSortKey] = useState("progress_desc");

  // Assign plan
  // Topic picker (giống giao đề) - Option B: cho phép chọn nhiều topic
  const [docs, setDocs] = useState([]);
  const [selectedDocIds, setSelectedDocIds] = useState([]);
  const [topicsByDoc, setTopicsByDoc] = useState({});
  const [selectedTopics, setSelectedTopics] = useState([]);

  const [level, setLevel] = useState("beginner");
  const [daysTotal, setDaysTotal] = useState(7);
  const [minutesPerDay, setMinutesPerDay] = useState(35);
  const [assigning, setAssigning] = useState(false);
  const [assignMsg, setAssignMsg] = useState(null);

  const effectiveDocIds = useMemo(() => {
    return (selectedDocIds || []).map((x) => Number(x)).filter((n) => Number.isFinite(n) && n > 0);
  }, [selectedDocIds]);

  const effectiveTopics = useMemo(() => {
    return (selectedTopics || []).map((s) => String(s)).filter(Boolean);
  }, [selectedTopics]);

  const loadDocs = async () => {
    try {
      const data = await apiJson("/documents");
      const arr = data?.documents || [];
      setDocs(Array.isArray(arr) ? arr : []);
    } catch {
      // ignore
    }
  };

  const refresh = async () => {
    setErr(null);
    setAssignMsg(null);
    setLoading(true);
    try {
      const [payload, reportPayload] = await Promise.all([
        apiJson(`/teacher/classrooms/${classroomId}/dashboard`),
        apiJson(`/lms/teacher/report/${classroomId}`),
      ]);
      setData(payload);
      setReport(reportPayload?.data || null);
    } catch (e) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!Number.isFinite(classroomId) || classroomId <= 0) return;
    refresh();
    loadDocs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classroomId]);

  // Fetch topics for selected documents
  useEffect(() => {
    (async () => {
      const missing = (selectedDocIds || []).filter((did) => !topicsByDoc[did]);
      if (missing.length === 0) return;
      try {
        const entries = await Promise.all(
          missing.map(async (did) => {
            const data = await apiJson(`/documents/${did}/topics`);
            return [did, data?.topics || []];
          })
        );
        setTopicsByDoc((prev) => {
          const next = { ...(prev || {}) };
          for (const [did, topics] of entries) next[did] = topics;
          return next;
        });
      } catch {
        // ignore
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDocIds]);

  const classroom = data?.classroom;
  const studentsRaw = Array.isArray(data?.students) ? data.students : [];

  const students = useMemo(() => {
    const q = (query || "").trim().toLowerCase();
    const mp = clamp(minProgress, 0, 100);
    const mh = clamp(minHomework, 0, 100);
    const th = clamp(needHelpThreshold, 0, 100);

    const mapped = studentsRaw.map((s) => {
      const total = Number(s?.tasks_total) || 0;
      const done = Number(s?.tasks_done) || 0;
      const progress = total > 0 ? (done / total) * 100 : 0;
      const hw = s?.homework_avg;
      const hwPct = typeof hw === "number" && Number.isFinite(hw) ? hw : null;
      return {
        ...s,
        _progress: clamp(progress, 0, 100),
        _homework: hwPct === null ? null : clamp(hwPct, 0, 100),
        _name: (s?.full_name || "").toLowerCase(),
      };
    });

    let out = mapped.filter((s) => {
      if (q) {
        const ok =
          String(s.user_id).includes(q) ||
          s._name.includes(q) ||
          (s.assigned_topic || "").toLowerCase().includes(q);
        if (!ok) return false;
      }

      if (s._progress < mp) return false;
      if (mh > 0) {
        if (s._homework === null) return false;
        if (s._homework < mh) return false;
      }

      if (needHelpOnly) {
        const hwVal = s._homework === null ? 0 : s._homework;
        if (!(s._progress < th || hwVal < th)) return false;
      }
      return true;
    });

    const cmpNum = (a, b, key) => (Number(a?.[key]) || 0) - (Number(b?.[key]) || 0);
    const cmpStr = (a, b, key) => String(a?.[key] || "").localeCompare(String(b?.[key] || ""));

    const sorters = {
      progress_desc: (a, b) => cmpNum(b, a, "_progress"),
      progress_asc: (a, b) => cmpNum(a, b, "_progress"),
      homework_desc: (a, b) => cmpNum(b, a, "_homework"),
      homework_asc: (a, b) => cmpNum(a, b, "_homework"),
      id_asc: (a, b) => cmpNum(a, b, "user_id"),
      name_asc: (a, b) => cmpStr(a, b, "full_name"),
    };

    out.sort(sorters[sortKey] || sorters.progress_desc);
    return out;
  }, [studentsRaw, query, minProgress, minHomework, needHelpOnly, needHelpThreshold, sortKey]);

  const stats = useMemo(() => {
    const totalStudents = studentsRaw.length;
    const assigned = studentsRaw.filter((s) => s.latest_plan_id).length;
    const withPlans = studentsRaw.filter((s) => Number(s?.tasks_total) > 0).length;

    const progressVals = studentsRaw
      .map((s) => {
        const total = Number(s?.tasks_total) || 0;
        const done = Number(s?.tasks_done) || 0;
        return total > 0 ? (done / total) * 100 : null;
      })
      .filter((x) => typeof x === "number" && Number.isFinite(x));

    const avgProgress = progressVals.length ? progressVals.reduce((a, b) => a + b, 0) / progressVals.length : 0;

    const hwVals = studentsRaw
      .map((s) => s?.homework_avg)
      .filter((x) => typeof x === "number" && Number.isFinite(x));
    const avgHomework = hwVals.length ? hwVals.reduce((a, b) => a + b, 0) / hwVals.length : 0;

    const th = clamp(needHelpThreshold, 0, 100);
    const needHelpCount = studentsRaw.filter((s) => {
      const total = Number(s?.tasks_total) || 0;
      const done = Number(s?.tasks_done) || 0;
      const progress = total > 0 ? (done / total) * 100 : 0;
      const hw = typeof s?.homework_avg === "number" ? s.homework_avg : 0;
      return progress < th || hw < th;
    }).length;

    return {
      totalStudents,
      assigned,
      withPlans,
      avgProgress: clamp(avgProgress, 0, 100),
      avgHomework: clamp(avgHomework, 0, 100),
      needHelpCount,
    };
  }, [studentsRaw, needHelpThreshold]);

  const chartCategories = useMemo(() => {
    const top = students.slice(0, 12);
    return top.map((s) => ({
      key: String(s.user_id),
      label: `#${s.user_id}`,
      progress: clamp(s._progress, 0, 100),
      homework: clamp(s._homework === null ? 0 : s._homework, 0, 100),
    }));
  }, [students]);

  const masteryItems = useMemo(() => {
    return students.slice(0, 14).map((s) => ({
      key: String(s.user_id),
      label: s.full_name ? `${s.full_name}` : `User #${s.user_id}`,
      value: (Number(s._progress) || 0) / 100,
    }));
  }, [students]);

  const copyJoinCode = async () => {
    const code = classroom?.join_code;
    if (!code) return;
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(String(code));
        setAssignMsg("✅ Đã copy join code");
      }
    } catch {
      // ignore
    }
  };

  const assignPlan = async () => {
    setAssignMsg(null);
    setErr(null);
    setAssigning(true);
    try {
      const body = {
        // Option B: join nhiều topic thành 1 chuỗi để backend build plan theo trọng tâm
        assigned_topic: effectiveTopics.length ? effectiveTopics.join("; ") : null,
        level,
        days_total: Number(daysTotal) || 7,
        minutes_per_day: Number(minutesPerDay) || 35,
      };
      const res = await apiJson(`/teacher/classrooms/${classroomId}/assign-learning-plan`, { method: "POST", body });
      const created = Array.isArray(res?.created) ? res.created.length : 0;
      setAssignMsg(`✅ Đã giao plan cho ${created} học sinh`);
      await refresh();
    } catch (e) {
      setErr(e?.message || String(e));
    } finally {
      setAssigning(false);
    }
  };

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ display: "grid", gap: 6 }}>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <Link to="/teacher/classrooms" style={{ display: "inline-flex", alignItems: "center", gap: 8, textDecoration: "none", color: "#111", fontWeight: 900 }}>
              <FaArrowLeft />
              Lớp học
            </Link>
            <span style={{ color: "#bbb" }}>·</span>
            <h1 style={{ margin: 0 }}>{classroom?.name || "Dashboard"}</h1>
          </div>

          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", color: "#555" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <FaUsers /> {stats.totalStudents} học sinh
            </span>
            {classroom?.join_code ? (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                Join code: <b style={{ letterSpacing: 1 }}>{classroom.join_code}</b>
                <button
                  onClick={copyJoinCode}
                  style={{ border: "1px solid #e6e6e6", background: "#fff", borderRadius: 10, padding: "6px 8px", cursor: "pointer" }}
                  title="Copy"
                >
                  <FaClipboard />
                </button>
              </span>
            ) : null}
          </div>
        </div>

        <button
          onClick={refresh}
          disabled={loading}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            padding: "10px 12px",
            borderRadius: 12,
            border: "1px solid #e6e6e6",
            background: "#fff",
            fontWeight: 900,
            cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          <FaSyncAlt />
          {loading ? "Đang tải..." : "Refresh"}
        </button>
      </div>

      {err ? (
        <div style={{ marginTop: 12, background: "#fff5f5", border: "1px solid #ffd6d6", padding: 12, borderRadius: 12, color: "#8a1f1f" }}>{err}</div>
      ) : null}

      {assignMsg ? (
        <div style={{ marginTop: 12, background: "#f6fff6", border: "1px solid #d8ffd8", padding: 12, borderRadius: 12, color: "#145214" }}>{assignMsg}</div>
      ) : null}

      {report ? (
        <div style={{ marginTop: 14 }}>
          <AINarrativeCard narrative={report.ai_narrative} />
          <ProgressChart data={report.progress_chart} />
          <WeakTopicsTable topics={report.weak_topics} />
        </div>
      ) : null}

      {/* Stats */}
      <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
        <StatCard title="Học sinh" value={stats.totalStudents} hint={`${stats.assigned} đã được giao plan`} />
        <StatCard title="Progress trung bình" value={`${Math.round(stats.avgProgress)}%`} hint={`${stats.withPlans} có dữ liệu tasks`} />
        <StatCard title="Homework trung bình" value={`${Math.round(stats.avgHomework)}%`} hint="tính trên bài đã nộp" />
        <StatCard title="Cần hỗ trợ" value={stats.needHelpCount} hint={`ngưỡng ${Math.round(clamp(needHelpThreshold, 0, 100))}%`} />
      </div>

      {/* Charts */}
      <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 14, alignItems: "start" }}>
        <GroupedBarChart
          title="So sánh Progress & Homework (top 12 theo filter)"
          subtitle="Progress = tasks_done/tasks_total · Homework = điểm trung bình tự luận"
          categories={chartCategories}
          series={[
            { key: "progress", label: "Progress" },
            { key: "homework", label: "Homework" },
          ]}
          maxValue={100}
          height={280}
        />
        <HorizontalBarList title="Progress nhanh (top 14)" items={masteryItems} threshold={clamp(needHelpThreshold, 0, 100) / 100} />
      </div>

      {/* Filters + Assign */}
      <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, alignItems: "start" }}>
        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
            <div style={{ fontWeight: 1000, fontSize: 16, display: "inline-flex", alignItems: "center", gap: 8 }}>
              <FaFilter /> Bộ lọc
            </div>
            <div style={{ color: "#666", fontSize: 12 }}>{students.length}/{studentsRaw.length} hiển thị</div>
          </div>

          <div style={{ marginTop: 12, display: "grid", gap: 12 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 8 }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <FaSearch style={{ color: "#777" }} />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Tìm theo tên/ID/topic"
                  style={{ width: "100%", padding: 10, borderRadius: 12, border: "1px solid #ddd" }}
                />
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <div style={{ fontWeight: 900, color: "#555", marginBottom: 6 }}>Min Progress: {Math.round(clamp(minProgress, 0, 100))}%</div>
                <input type="range" min="0" max="100" value={minProgress} onChange={(e) => setMinProgress(Number(e.target.value))} style={{ width: "100%" }} />
              </div>
              <div>
                <div style={{ fontWeight: 900, color: "#555", marginBottom: 6 }}>Min Homework: {Math.round(clamp(minHomework, 0, 100))}%</div>
                <input type="range" min="0" max="100" value={minHomework} onChange={(e) => setMinHomework(Number(e.target.value))} style={{ width: "100%" }} />
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, alignItems: "center" }}>
              <div>
                <div style={{ fontWeight: 900, color: "#555", marginBottom: 6 }}>Ngưỡng cần hỗ trợ: {Math.round(clamp(needHelpThreshold, 0, 100))}%</div>
                <input type="range" min="0" max="100" value={needHelpThreshold} onChange={(e) => setNeedHelpThreshold(Number(e.target.value))} style={{ width: "100%" }} />
              </div>

              <div style={{ display: "grid", gap: 8 }}>
                <label style={{ display: "flex", gap: 10, alignItems: "center", fontWeight: 900, color: "#333" }}>
                  <input type="checkbox" checked={needHelpOnly} onChange={(e) => setNeedHelpOnly(e.target.checked)} />
                  Chỉ hiển thị HS cần hỗ trợ
                </label>

                <div>
                  <div style={{ fontWeight: 900, color: "#555", marginBottom: 6 }}>Sắp xếp</div>
                  <select value={sortKey} onChange={(e) => setSortKey(e.target.value)} style={{ width: "100%", padding: 10, borderRadius: 12, border: "1px solid #ddd", background: "#fff" }}>
                    <option value="progress_desc">Progress ↓</option>
                    <option value="progress_asc">Progress ↑</option>
                    <option value="homework_desc">Homework ↓</option>
                    <option value="homework_asc">Homework ↑</option>
                    <option value="name_asc">Tên A→Z</option>
                    <option value="id_asc">ID ↑</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
        </Card>

        <Card>
          <div style={{ fontWeight: 1000, fontSize: 16, display: "inline-flex", alignItems: "center", gap: 8 }}>
            <FaPaperPlane /> Giao learning plan cho cả lớp
          </div>
          <div style={{ marginTop: 12, display: "grid", gap: 12 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <div style={{ fontWeight: 900, color: "#555", marginBottom: 6 }}>Topic (chọn từ tài liệu)</div>
                <div style={{ color: "#666", fontSize: 12, lineHeight: 1.4 }}>
                  Chọn tài liệu → chọn nhiều topic. Nếu bỏ trống, hệ thống tạo plan tổng quát.
                </div>
              </div>
              <div>
                <div style={{ fontWeight: 900, color: "#555", marginBottom: 6 }}>Level</div>
                <select value={level} onChange={(e) => setLevel(e.target.value)} style={{ width: "100%", padding: 10, borderRadius: 12, border: "1px solid #ddd", background: "#fff" }}>
                  <option value="beginner">beginner</option>
                  <option value="intermediate">intermediate</option>
                  <option value="advanced">advanced</option>
                </select>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <div style={{ fontWeight: 900, color: "#555", marginBottom: 6 }}>Chọn tài liệu</div>
                <div style={{ display: "grid", gap: 8, maxHeight: 180, overflow: "auto", border: "1px solid #eee", borderRadius: 12, padding: 10 }}>
                  {(docs || []).length === 0 ? <div style={{ color: "#666" }}>Chưa có tài liệu. Hãy upload trước.</div> : null}
                  {(docs || []).map((d) => {
                    const did = Number(d.document_id);
                    const checked = (selectedDocIds || []).includes(did);
                    return (
                      <label key={did} style={{ display: "flex", gap: 10, alignItems: "center" }}>
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => {
                            setSelectedDocIds((prev) => {
                              const cur = Array.isArray(prev) ? prev : [];
                              if (cur.includes(did)) return cur.filter((x) => x !== did);
                              return [...cur, did];
                            });
                          }}
                        />
                        <span>
                          <b>{d.title}</b> <span style={{ color: "#666" }}>(id={did})</span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>

              <div>
                <div style={{ fontWeight: 900, color: "#555", marginBottom: 6 }}>
                  Chọn topic ({effectiveTopics.length})
                </div>
                <div style={{ display: "grid", gap: 8, maxHeight: 180, overflow: "auto", border: "1px solid #eee", borderRadius: 12, padding: 10 }}>
                  {effectiveDocIds.length === 0 ? <div style={{ color: "#666" }}>Chọn ít nhất 1 tài liệu để hiện topic.</div> : null}
                  {effectiveDocIds.length > 0 && (
                    <>
                      {effectiveDocIds.flatMap((did) => {
                        const tps = topicsByDoc[did] || [];
                        const docTitle = (docs || []).find((x) => Number(x.document_id) === Number(did))?.title || `Doc ${did}`;
                        return (tps || []).map((t) => {
                          const key = `${did}::${t.topic_id || t.title}`;
                          const title = String(t.title);
                          const checked = (selectedTopics || []).includes(title);
                          const no = Number.isFinite(Number(t.topic_index)) ? Number(t.topic_index) + 1 : null;
                          return (
                            <label key={key} style={{ display: "flex", gap: 10, alignItems: "center" }}>
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => {
                                  setSelectedTopics((prev) => {
                                    const cur = Array.isArray(prev) ? prev : [];
                                    if (cur.includes(title)) return cur.filter((x) => x !== title);
                                    return [...cur, title];
                                  });
                                }}
                              />
                              <span>
                                <span style={{ color: "#666" }}>{docTitle}{no ? ` — Chủ đề ${no}:` : ":"}</span> {title}
                              </span>
                            </label>
                          );
                        });
                      })}
                      {effectiveDocIds.length > 0 && effectiveDocIds.flatMap((did) => topicsByDoc[did] || []).length === 0 ? (
                        <div style={{ color: "#666" }}>Tài liệu chưa có topic tự động. Bạn có thể bỏ trống để tạo plan tổng quát.</div>
                      ) : null}
                    </>
                  )}
                </div>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <div style={{ fontWeight: 900, color: "#555", marginBottom: 6 }}>Số ngày</div>
                <input type="number" min="1" max="30" value={daysTotal} onChange={(e) => setDaysTotal(Number(e.target.value))} style={{ width: "100%", padding: 10, borderRadius: 12, border: "1px solid #ddd" }} />
              </div>
              <div>
                <div style={{ fontWeight: 900, color: "#555", marginBottom: 6 }}>Phút/ngày</div>
                <input type="number" min="10" max="180" value={minutesPerDay} onChange={(e) => setMinutesPerDay(Number(e.target.value))} style={{ width: "100%", padding: 10, borderRadius: 12, border: "1px solid #ddd" }} />
              </div>
            </div>

            <button
              onClick={assignPlan}
              disabled={assigning || stats.totalStudents === 0}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 10,
                padding: "11px 14px",
                borderRadius: 12,
                border: "1px solid #e6e6e6",
                background: assigning ? "#f3f3f3" : "#111",
                color: assigning ? "#888" : "#fff",
                fontWeight: 1000,
                cursor: assigning ? "not-allowed" : "pointer",
              }}
            >
              <FaChartLine />
              {assigning ? "Đang giao..." : "Giao plan"}
            </button>

            <div style={{ color: "#666", lineHeight: 1.5 }}>
              Hệ thống tạo plan dựa theo tài liệu của teacher và lưu plan cho từng học sinh.
            </div>
          </div>
        </Card>
      </div>

      {/* Table */}
      <Card style={{ marginTop: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
          <div style={{ fontWeight: 1000, fontSize: 16, display: "inline-flex", alignItems: "center", gap: 10 }}>
            <FaUsers /> Danh sách học sinh
          </div>
          <div style={{ color: "#666" }}>
            <b>{students.length}</b> / {studentsRaw.length}
          </div>
        </div>

        <div style={{ marginTop: 12, overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #eee" }}>
                <th style={{ padding: 10 }}>Học sinh</th>
                <th style={{ padding: 10 }}>Progress</th>
                <th style={{ padding: 10 }}>Homework avg</th>
                <th style={{ padding: 10 }}>Plan</th>
                <th style={{ padding: 10 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {students.map((s) => {
                const hw = s._homework;
                const hwText = hw === null ? "—" : `${Math.round(hw)}%`;
                const prog = s._progress;
                const total = Number(s?.tasks_total) || 0;
                const done = Number(s?.tasks_done) || 0;
                const plan = s.latest_plan_id ? `#${s.latest_plan_id}` : "—";
                return (
                  <tr key={s.user_id} style={{ borderBottom: "1px solid #f3f3f3" }}>
                    <td style={{ padding: 10 }}>
                      <div style={{ fontWeight: 1000 }}>{s.full_name || `User #${s.user_id}`}</div>
                      <div style={{ color: "#666", fontSize: 12 }}>
                        ID: <b>{s.user_id}</b>
                      </div>
                      {s.assigned_topic ? <div style={{ color: "#666", fontSize: 12 }}>Topic: {s.assigned_topic}</div> : null}
                    </td>

                    <td style={{ padding: 10, minWidth: 240 }}>
                      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                        <div style={{ flex: 1, height: 10, background: "#f2f2f2", borderRadius: 999, position: "relative" }}>
                          <div style={{ width: `${Math.round(prog)}%`, height: 10, borderRadius: 999, background: prog >= 70 ? "#111" : "#999" }} />
                        </div>
                        <ProgressPill pct={prog} />
                      </div>
                      <div style={{ color: "#666", fontSize: 12, marginTop: 6 }}>
                        {done}/{total} tasks
                      </div>
                    </td>

                    <td style={{ padding: 10 }}>
                      <div style={{ fontWeight: 1000 }}>{hwText}</div>
                      <div style={{ color: "#666", fontSize: 12 }}>{s.last_homework_score == null ? "" : `Lần cuối: ${Math.round(s.last_homework_score)}%`}</div>
                    </td>

                    <td style={{ padding: 10, fontWeight: 900 }}>{plan}</td>

                    <td style={{ padding: 10 }}>
                      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                        <Link
                          to={`/teacher/progress/${s.user_id}?classroom_id=${classroomId}`}
                          style={{
                            padding: "9px 11px",
                            borderRadius: 12,
                            border: "1px solid #e6e6e6",
                            background: "#fff",
                            color: "#111",
                            textDecoration: "none",
                            fontWeight: 900,
                          }}
                        >
                          Xem tiến độ
                        </Link>

                        <Link
                          to={`/teacher/student-plan/${s.user_id}?classroom_id=${classroomId}`}
                          style={{
                            padding: "9px 11px",
                            borderRadius: 12,
                            border: "1px solid #e6e6e6",
                            background: "#fff",
                            color: "#111",
                            textDecoration: "none",
                            fontWeight: 900,
                          }}
                        >
                          Xem Learning Path
                        </Link>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {students.length === 0 ? <div style={{ marginTop: 10, color: "#666" }}>Không có học sinh phù hợp bộ lọc.</div> : null}
        </div>
      </Card>
    </div>
  );
}
