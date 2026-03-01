import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiJson } from "../lib/api";

const KIND_BADGES = {
  diagnostic_pre: { label: "Đầu vào", bg: "#e0f2fe", color: "#075985" },
  midterm: { label: "Bài tổng hợp", bg: "#dcfce7", color: "#166534" },
  diagnostic_post: { label: "Cuối kỳ", bg: "#ede9fe", color: "#5b21b6" },
};

export default function Assessments() {
  const [classrooms, setClassrooms] = useState([]);
  const [classroomId, setClassroomId] = useState(() => {
    const v = localStorage.getItem("active_classroom_id");
    const n = v ? Number(v) : null;
    return Number.isFinite(n) && n > 0 ? n : null;
  });
  const [kindFilter, setKindFilter] = useState("all");

  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const classroomMap = useMemo(() => {
    const m = new Map();
    (classrooms || []).forEach((c) => m.set(Number(c.id), c));
    return m;
  }, [classrooms]);

  const filteredList = useMemo(() => {
    if (kindFilter === "all") return list;
    return list.filter((it) => String(it?.kind || "").toLowerCase() === kindFilter);
  }, [list, kindFilter]);

  const loadClassrooms = async () => {
    try {
      const rows = await apiJson("/classrooms");
      const arr = Array.isArray(rows) ? rows : [];
      setClassrooms(arr);
      if (!classroomId && arr.length > 0) {
        setClassroomId(Number(arr[0].id));
      }
    } catch {
      // ignore
    }
  };

  const loadAssessments = async (cid = classroomId) => {
    if (!cid) {
      setList([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await apiJson(`/assessments?classroom_id=${Number(cid)}`);
      setList(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(e?.message || "Không load được danh sách");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadClassrooms();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (classroomId) {
      localStorage.setItem("active_classroom_id", String(classroomId));
      loadAssessments(classroomId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classroomId]);

  return (
    <div style={{ maxWidth: 980, margin: "0 auto", padding: 16 }}>
      <h2>📝 Danh sách bài kiểm tra</h2>

      <div style={{ marginBottom: 10 }}>
        <Link to="/final-exam" style={{ textDecoration: "none" }}>
          <button style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid #c4b5fd", background: "#f5f3ff", color: "#5b21b6", fontWeight: 700 }}>
            🎓 Tới trang Bài kiểm tra Cuối kỳ
          </button>
        </Link>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ color: "#666" }}>Lớp:</span>
          <select value={classroomId || ""} onChange={(e) => setClassroomId(e.target.value ? Number(e.target.value) : null)} style={{ padding: 8, borderRadius: 10, border: "1px solid #ddd" }}>
            <option value="">-- Chọn lớp --</option>
            {(classrooms || []).map((c) => (
              <option key={c.id} value={c.id}>#{c.id} • {c.name}</option>
            ))}
          </select>

          <span style={{ color: "#666" }}>Loại:</span>
          <select value={kindFilter} onChange={(e) => setKindFilter(e.target.value)} style={{ padding: 8, borderRadius: 10, border: "1px solid #ddd" }}>
            <option value="all">Tất cả</option>
            <option value="diagnostic_pre">Đầu vào</option>
            <option value="midterm">Bài tổng hợp</option>
            <option value="diagnostic_post">Cuối kỳ</option>
          </select>
        </div>
        <button onClick={() => loadAssessments(classroomId)} disabled={!classroomId || loading} style={{ padding: "8px 12px" }}>Refresh</button>
      </div>

      {error ? <div style={{ marginTop: 12, background: "#fff5f5", border: "1px solid #ffd6d6", padding: 12, borderRadius: 12, color: "#8a1f1f" }}>{error}</div> : null}
      {loading ? <div style={{ marginTop: 12, color: "#666" }}>Đang tải…</div> : null}

      <div style={{ display: "grid", gap: 12, marginTop: 12 }}>
        {filteredList.map((it) => {
          const cls = classroomMap.get(Number(it.classroom_id));
          const classLabel = cls ? `#${cls.id} • ${cls.name}` : `#${it.classroom_id}`;
          const badge = KIND_BADGES[String(it?.kind || "").toLowerCase()] || { label: it?.kind || "Khác", bg: "#f3f4f6", color: "#374151" };
          return (
            <div key={it.assessment_id} style={{ background: "#fff", borderRadius: 12, padding: 12, boxShadow: "0 2px 10px rgba(0,0,0,0.06)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                <div>
                  <div style={{ fontWeight: 900, display: "flex", alignItems: "center", gap: 8 }}>
                    {it.title}
                    <span style={{ padding: "3px 8px", borderRadius: 999, background: badge.bg, color: badge.color, fontSize: 12, fontWeight: 700 }}>{badge.label}</span>
                  </div>
                  <div style={{ color: "#666" }}>Lớp: {classLabel} • Level: {it.level} • Created: {it.created_at}</div>
                </div>
                <Link to={`/assessments/${it.assessment_id}${String(it?.kind || "") === "diagnostic_post" ? "?mode=final" : ""}`} state={String(it?.kind || "") === "diagnostic_post" ? { examMode: "final" } : undefined} style={{ textDecoration: "none" }}>
                  <button style={{ padding: "8px 12px" }}>Làm bài</button>
                </Link>
              </div>
            </div>
          );
        })}

        {!loading && (!classroomId ? <div style={{ color: "#666" }}>Chọn lớp để xem bài được giao.</div> : filteredList.length === 0 ? <div style={{ color: "#666" }}>Không có bài kiểm tra cho bộ lọc hiện tại.</div> : null)}
      </div>
    </div>
  );
}
