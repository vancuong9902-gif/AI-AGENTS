import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiJson } from "../lib/api";
import { FaSchool, FaSearch, FaUsers } from "react-icons/fa";

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

export default function StudentClassrooms() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [msg, setMsg] = useState(null);

  const [code, setCode] = useState("");
  const [joining, setJoining] = useState(false);
  const [activeId, setActiveId] = useState(() => {
    const v = localStorage.getItem("active_classroom_id");
    const n = v ? Number(v) : null;
    return Number.isFinite(n) && n > 0 ? n : null;
  });

  const refresh = async () => {
    setError(null);
    setLoading(true);
    try {
      const data = await apiJson("/classrooms");
      setRows(Array.isArray(data) ? data : []);
      const arr = Array.isArray(data) ? data : [];
      // default active classroom
      if (!activeId && arr.length > 0) {
        const cid = Number(arr[0].id);
        setActiveId(cid);
        localStorage.setItem("active_classroom_id", String(cid));
      }
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  const chooseActive = (cid) => {
    const n = Number(cid);
    if (!Number.isFinite(n) || n <= 0) return;
    setActiveId(n);
    localStorage.setItem("active_classroom_id", String(n));
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const join = async () => {
    const jc = (code || "").trim();
    if (!jc) return;
    setMsg(null);
    setError(null);
    setJoining(true);
    try {
      const r = await apiJson("/classrooms/join", { method: "POST", body: { join_code: jc } });
      setMsg(`✅ Đã tham gia lớp: ${r?.name || "(ok)"}`);
      setCode("");
      await refresh();
    } catch (e) {
      setError(e?.message || String(e));
    } finally {
      setJoining(false);
    }
  };

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <FaSchool />
          <h1 style={{ margin: 0 }}>Lớp của tôi</h1>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <Link to="/assessments" style={{ textDecoration: "none", fontWeight: 900, color: "#111" }}>
            📝 Bài tổng hợp
          </Link>
          <Link to="/learning-path" style={{ textDecoration: "none", fontWeight: 900, color: "#111" }}>
            📌 Learning Path
          </Link>
        </div>
      </div>

      {error ? (
        <div style={{ marginTop: 12, background: "#fff5f5", border: "1px solid #ffd6d6", padding: 12, borderRadius: 12, color: "#8a1f1f" }}>{error}</div>
      ) : null}
      {msg ? (
        <div style={{ marginTop: 12, background: "#f6fff6", border: "1px solid #d8ffd8", padding: 12, borderRadius: 12, color: "#145214" }}>{msg}</div>
      ) : null}

      <Card style={{ marginTop: 14 }}>
        <div style={{ fontWeight: 1000, fontSize: 16 }}>Tham gia lớp bằng Join code</div>
        <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flex: "1 1 320px" }}>
            <FaSearch style={{ color: "#777" }} />
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="VD: DEMO123"
              style={{ width: "100%", padding: 11, borderRadius: 12, border: "1px solid #ddd" }}
            />
          </div>
          <button
            onClick={join}
            disabled={joining || !(code || "").trim()}
            style={{
              padding: "11px 14px",
              borderRadius: 12,
              border: "1px solid #e6e6e6",
              background: joining ? "#f3f3f3" : "#111",
              color: joining ? "#888" : "#fff",
              fontWeight: 1000,
              cursor: joining ? "not-allowed" : "pointer",
            }}
          >
            {joining ? "Đang join..." : "Join"}
          </button>
        </div>
        <div style={{ marginTop: 10, color: "#666" }}>
          Tip: Project đã tạo sẵn lớp demo (teacher ID=1) với code <b>DEMO123</b>.
        </div>
      </Card>

      <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>
        {rows.map((c) => (
          <Card key={c.id}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "start" }}>
              <div style={{ display: "grid", gap: 6 }}>
                <div style={{ fontWeight: 1000, fontSize: 18 }}>{c.name}</div>
                <div style={{ color: "#666" }}>Teacher: #{c.teacher_id}</div>
              </div>
              <div style={{ display: "inline-flex", alignItems: "center", gap: 8, color: "#333", fontWeight: 900 }}>
                <FaUsers /> {c.student_count}
              </div>
            </div>

            <div style={{ marginTop: 12, color: "#666", lineHeight: 1.5 }}>
              Sau khi teacher giao plan, bạn vào <b>Learning Path</b> để làm nhiệm vụ từng ngày.
            </div>

            <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button
                onClick={() => chooseActive(c.id)}
                style={{
                  padding: "10px 12px",
                  borderRadius: 12,
                  background: Number(activeId) === Number(c.id) ? "#111" : "#fff",
                  border: "1px solid #e6e6e6",
                  color: Number(activeId) === Number(c.id) ? "#fff" : "#111",
                  fontWeight: 1000,
                  cursor: "pointer",
                }}
              >
                {Number(activeId) === Number(c.id) ? "✅ Lớp hiện tại" : "Chọn làm lớp hiện tại"}
              </button>
              <Link
                to="/learning-path"
                style={{
                  padding: "10px 12px",
                  borderRadius: 12,
                  background: "#fff",
                  border: "1px solid #e6e6e6",
                  color: "#111",
                  textDecoration: "none",
                  fontWeight: 1000,
                }}
              >
                Mở Learning Path
              </Link>
              <Link
                to="/assessments"
                style={{
                  padding: "10px 12px",
                  borderRadius: 12,
                  background: "#111",
                  color: "#fff",
                  textDecoration: "none",
                  fontWeight: 1000,
                }}
              >
                Làm bài tổng hợp
              </Link>
            </div>
          </Card>
        ))}

        {!loading && rows.length === 0 ? (
          <Card>
            <div style={{ fontWeight: 1000 }}>Bạn chưa tham gia lớp nào</div>
            <div style={{ marginTop: 8, color: "#666" }}>Nhập join code để tham gia (VD: DEMO123).</div>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
