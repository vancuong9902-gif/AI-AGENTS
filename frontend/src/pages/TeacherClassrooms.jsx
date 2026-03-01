import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiJson } from "../lib/api";
import { FaChalkboardTeacher, FaPlus, FaSyncAlt, FaUsers } from "react-icons/fa";

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

function StatPill({ icon, label }) {
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "8px 10px",
        borderRadius: 999,
        border: "1px solid #eee",
        background: "#fafafa",
        color: "#333",
        fontWeight: 800,
        fontSize: 12,
      }}
    >
      {icon}
      <span>{label}</span>
    </div>
  );
}

export default function TeacherClassrooms() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);

  const refresh = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const data = await apiJson("/teacher/classrooms");
      setRows(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const totals = useMemo(() => {
    const classrooms = rows.length;
    const students = rows.reduce((acc, r) => acc + (Number(r?.student_count) || 0), 0);
    return { classrooms, students };
  }, [rows]);

  const createClassroom = async () => {
    const n = (name || "").trim();
    if (!n) return;
    setError(null);
    setCreating(true);
    try {
      await apiJson("/teacher/classrooms", { method: "POST", body: { name: n } });
      setName("");
      await refresh();
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setCreating(false);
    }
  };

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ display: "grid", gap: 6 }}>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <FaChalkboardTeacher />
            <h1 style={{ margin: 0 }}>Lớp học</h1>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <StatPill icon={<FaUsers />} label={`${totals.students} học sinh`} />
            <StatPill icon={<span style={{ fontWeight: 900 }}>🏫</span>} label={`${totals.classrooms} lớp`} />
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
            fontWeight: 800,
            cursor: loading ? "not-allowed" : "pointer",
          }}
          title="Tải lại"
        >
          <FaSyncAlt />
          {loading ? "Đang tải..." : "Refresh"}
        </button>
      </div>

      {error ? (
        <div style={{ marginTop: 12, background: "#fff5f5", border: "1px solid #ffd6d6", padding: 12, borderRadius: 12, color: "#8a1f1f" }}>
          {error}
        </div>
      ) : null}

      <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr", gap: 14 }}>
        <Card>
          <div style={{ fontWeight: 900, fontSize: 16 }}>Tạo lớp mới</div>
          <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="VD: Lớp 12A1"
              style={{ flex: "1 1 320px", padding: 11, borderRadius: 12, border: "1px solid #ddd" }}
            />
            <button
              onClick={createClassroom}
              disabled={creating || !(name || "").trim()}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                padding: "11px 14px",
                borderRadius: 12,
                border: "1px solid #e6e6e6",
                background: creating ? "#f3f3f3" : "#111",
                color: creating ? "#888" : "#fff",
                fontWeight: 900,
                cursor: creating ? "not-allowed" : "pointer",
              }}
            >
              <FaPlus />
              {creating ? "Đang tạo..." : "Tạo lớp"}
            </button>
          </div>
          <div style={{ marginTop: 10, color: "#666", lineHeight: 1.5 }}>
            Học sinh join bằng <b>Join code</b>. Bạn có thể giao learning plan cho cả lớp và theo dõi dashboard.
          </div>
        </Card>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>
          {rows.map((c) => (
            <Card key={c.id}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "start" }}>
                <div style={{ display: "grid", gap: 6 }}>
                  <div style={{ fontWeight: 1000, fontSize: 18 }}>{c.name}</div>
                  <div style={{ color: "#666" }}>
                    Join code: <b style={{ letterSpacing: 1 }}>{c.join_code}</b>
                  </div>
                </div>
                <div style={{ display: "inline-flex", alignItems: "center", gap: 8, color: "#333", fontWeight: 900 }}>
                  <FaUsers />
                  {c.student_count}
                </div>
              </div>

              <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap" }}>
                <Link
                  to={`/teacher/classrooms/${c.id}`}
                  style={{
                    padding: "10px 12px",
                    borderRadius: 12,
                    background: "#111",
                    color: "#fff",
                    textDecoration: "none",
                    fontWeight: 900,
                  }}
                >
                  Dashboard
                </Link>
                <Link
                  to={`/teacher/classrooms/${c.id}`}
                  style={{
                    padding: "10px 12px",
                    borderRadius: 12,
                    background: "#fff",
                    border: "1px solid #e6e6e6",
                    color: "#111",
                    textDecoration: "none",
                    fontWeight: 900,
                  }}
                >
                  Giao learning plan
                </Link>
              </div>
            </Card>
          ))}

          {!loading && rows.length === 0 ? (
            <Card>
              <div style={{ fontWeight: 900 }}>Chưa có lớp nào</div>
              <div style={{ marginTop: 8, color: "#666" }}>Tạo lớp mới ở phía trên để bắt đầu.</div>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  );
}
