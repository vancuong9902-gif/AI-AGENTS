import { useEffect, useMemo, useState } from "react";
import { apiJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { GroupedBarChart, HorizontalBarList } from "../components/Charts";
import { useNavigate, useParams } from "react-router-dom";

function toPct(v) {
  const n = Number(v);
  return Number.isFinite(n) ? Math.round(n) : null;
}

function fmtDelta(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `${n > 0 ? "+" : ""}${n}`;
}

export default function Progress() {
  const { userId, role } = useAuth();
  const navigate = useNavigate();
  const params = useParams();

  // Target student
  const initialTargetId = (() => {
    const raw = role === "teacher" ? params.studentId : userId;
    const n = Number(raw ?? 1);
    return Number.isFinite(n) && n > 0 ? n : 1;
  })();

  // Classroom scope (important because mỗi lớp có bài riêng)
  const initialClassroomId = (() => {
    const qs = new URLSearchParams(window.location.search);
    const q = qs.get("classroom_id");
    const n = q ? Number(q) : null;
    if (Number.isFinite(n) && n > 0) return n;
    const v = localStorage.getItem("teacher_active_classroom_id");
    const n2 = v ? Number(v) : null;
    return Number.isFinite(n2) && n2 > 0 ? n2 : null;
  })();

  const [targetUserId, setTargetUserId] = useState(initialTargetId);
  const [inputId, setInputId] = useState(String(initialTargetId));
  const [classrooms, setClassrooms] = useState([]);
  const [classroomId, setClassroomId] = useState(initialClassroomId);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadClassrooms = async () => {
    if (role !== "teacher") return;
    try {
      const rows = await apiJson("/teacher/classrooms");
      const arr = Array.isArray(rows) ? rows : [];
      setClassrooms(arr);
      if (!classroomId && arr.length > 0) {
        setClassroomId(Number(arr[0].id));
      }
    } catch {
      // ignore
    }
  };

  const load = async (id = targetUserId, cid = classroomId) => {
    setLoading(true);
    setError("");
    try {
      const qs = cid ? `?classroom_id=${Number(cid)}` : "";
      const res = await apiJson(`/evaluation/${Number(id)}/overall${qs}`);
      setData(res);
    } catch (e) {
      setError(e?.message || "Không load được tiến bộ");
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setTargetUserId(initialTargetId);
    setInputId(String(initialTargetId));
    loadClassrooms();
    load(initialTargetId, initialClassroomId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialTargetId]);

  useEffect(() => {
    if (role !== "teacher") return;
    if (classroomId) {
      localStorage.setItem("teacher_active_classroom_id", String(classroomId));
    }
    // keep URL in sync (teacher only)
    if (role === "teacher") {
      const base = `/teacher/progress/${Number(targetUserId)}`;
      const url = classroomId ? `${base}?classroom_id=${Number(classroomId)}` : base;
      window.history.replaceState({}, "", url);
    }
    load(targetUserId, classroomId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classroomId]);

  const applyTarget = () => {
    const n = Number(inputId);
    if (!Number.isFinite(n) || n <= 0) return;
    setTargetUserId(n);
    const url = classroomId ? `/teacher/progress/${n}?classroom_id=${Number(classroomId)}` : `/teacher/progress/${n}`;
    navigate(url);
    load(n, classroomId);
  };

  // POST on dashboard = 50% midterm + 50% final (backend already returns post_weighted)
  const postDisplay = useMemo(() => {
    if (!data) return null;
    const pw = data?.post_weighted;
    if (pw && Number.isFinite(Number(pw?.score_percent))) return pw;
    return data?.post || null;
  }, [data]);

  const chartCats = useMemo(() => {
    const pre = data?.pre || {};
    const post = postDisplay || {};

    return [
      { key: "total", label: "Total", pre: toPct(pre.score_percent) ?? 0, post: toPct(post.score_percent) ?? 0 },
      { key: "mcq", label: "MCQ", pre: toPct(pre.mcq_score_percent) ?? 0, post: toPct(post.mcq_score_percent) ?? 0 },
      { key: "essay", label: "Essay", pre: toPct(pre.essay_score_percent) ?? 0, post: toPct(post.essay_score_percent) ?? 0 },
    ];
  }, [data, postDisplay]);

  // Weak topics (post)
  const weakTopics = useMemo(() => {
    const by = data?.post?.mastery?.by_topic;
    if (!by || typeof by !== "object") return [];
    const rows = Object.entries(by)
      .map(([k, v]) => ({ key: String(k), label: String(k), value: Number(v) }))
      .filter((x) => Number.isFinite(x.value))
      .sort((a, b) => (a.value ?? 0) - (b.value ?? 0))
      .slice(0, 10);
    // normalize 0..1
    return rows.map((r) => ({ ...r, value: Math.max(0, Math.min(1, r.value)) }));
  }, [data]);

  const prePct = toPct(data?.pre?.score_percent);
  const midPct = toPct(data?.midterm?.score_percent);
  const finalPct = toPct(data?.post?.score_percent);
  const overallPct = toPct(postDisplay?.score_percent);

  const classLabel = useMemo(() => {
    if (role !== "teacher") return null;
    const cls = (classrooms || []).find((c) => Number(c.id) === Number(classroomId));
    return cls ? `#${cls.id} • ${cls.name}` : classroomId ? `#${classroomId}` : "(tất cả lớp)";
  }, [classrooms, classroomId, role]);

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>📈 Progress Dashboard</h2>
          <div style={{ color: "#666" }}>Pre-test vs Điểm tổng kết (Post = 50% giữa khóa + 50% cuối khóa).</div>

          {role === "teacher" && (
            <div style={{ marginTop: 10, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ color: "#666" }}>Student ID:</span>
              <input value={inputId} onChange={(e) => setInputId(e.target.value)} placeholder="VD: 2" style={{ width: 120, padding: 8, borderRadius: 10, border: "1px solid #ddd" }} />
              <button onClick={applyTarget} disabled={loading} style={{ padding: "8px 12px" }}>
                Xem
              </button>

              <span style={{ color: "#666", marginLeft: 6 }}>Lớp:</span>
              <select
                value={classroomId || ""}
                onChange={(e) => setClassroomId(e.target.value ? Number(e.target.value) : null)}
                style={{ padding: 8, borderRadius: 10, border: "1px solid #ddd" }}
              >
                <option value="">-- (tất cả lớp) --</option>
                {(classrooms || []).map((c) => (
                  <option key={c.id} value={c.id}>
                    #{c.id} • {c.name}
                  </option>
                ))}
              </select>
              {classLabel ? <span style={{ color: "#888", fontSize: 13 }}>Đang xem: {classLabel}</span> : null}
            </div>
          )}
        </div>

        <button onClick={() => load(targetUserId, classroomId)} disabled={loading} style={{ padding: "8px 12px" }}>
          Refresh
        </button>
      </div>

      {error && <div style={{ marginTop: 12, background: "#fff3f3", border: "1px solid #ffd0d0", padding: 12, borderRadius: 12 }}>{error}</div>}
      {loading && <div style={{ marginTop: 12, color: "#666" }}>Đang tải…</div>}

      {!loading && data && (
        <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 14, alignItems: "start" }}>
          <GroupedBarChart
            title="Điểm số pre vs post"
            subtitle="Post = 50% giữa khóa + 50% cuối khóa (Total = 70% MCQ + 30% Essay)"
            categories={chartCats}
            series={[{ key: "pre", label: "Pre" }, { key: "post", label: "Post" }]}
            height={270}
            maxValue={100}
          />

          <div style={{ background: "#fff", borderRadius: 16, padding: 14, boxShadow: "0 2px 10px rgba(0,0,0,0.06)" }}>
            <div style={{ fontWeight: 900, fontSize: 16 }}>Tóm tắt</div>

            <div style={{ marginTop: 10, display: "grid", gap: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                <div style={{ color: "#666" }}>Pre-test</div>
                <div style={{ fontWeight: 900 }}>{prePct ?? "—"}% ({data?.pre?.level || "—"})</div>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                <div style={{ color: "#666" }}>Giữa khóa</div>
                <div style={{ fontWeight: 900 }}>
                  {midPct ?? "—"}%
                  {data?.midterm?.pending ? <span style={{ marginLeft: 8, color: "#b15b00" }}>(chờ chấm tự luận)</span> : null}
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                <div style={{ color: "#666" }}>Cuối khóa</div>
                <div style={{ fontWeight: 900 }}>{finalPct ?? "—"}% ({data?.post?.level || "—"})</div>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                <div style={{ color: "#666" }}>Post (Tổng kết 50/50)</div>
                <div style={{ fontWeight: 900 }}>{overallPct ?? "—"}% {postDisplay?.level ? `(${postDisplay.level})` : ""}</div>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                <div style={{ color: "#666" }}>Delta (Post - Pre)</div>
                <div style={{ fontWeight: 900 }}>{fmtDelta(data?.delta_score)}</div>
              </div>

              <div style={{ marginTop: 6, color: "#666" }}>{data?.message}</div>
            </div>
          </div>

          <HorizontalBarList title="Weak topics (Post)" items={weakTopics} threshold={0.6} />
        </div>
      )}
    </div>
  );
}
