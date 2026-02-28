import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const navigate = useNavigate();
  const { role, setRole, userId, setUserId, fullName, setFullName } = useAuth();

  const [localRole, setLocalRole] = useState(role || "student");
  const [localId, setLocalId] = useState(String(userId ?? 1));
  const [localName, setLocalName] = useState(fullName || "");

  const parsedId = useMemo(() => {
    const n = Number(localId);
    return Number.isFinite(n) && n > 0 ? Math.floor(n) : null;
  }, [localId]);

  const submit = (e) => {
    e?.preventDefault?.();
    if (!parsedId) return;
    setUserId(parsedId);
    setRole(localRole);
    setFullName((localName || "").trim() || null);

    // Default landing pages
    if (localRole === "teacher") navigate("/teacher/classrooms");
    else navigate("/classrooms");
  };

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: 16 }}>
      <h1>🔐 Demo Login (không email, không JWT)</h1>
      <p style={{ color: "#666", marginTop: 0 }}>
        Chọn <b>Role</b> và nhập <b>User ID</b> để sử dụng hệ thống.
      </p>

      <form onSubmit={submit} style={{ background: "#fff", borderRadius: 16, padding: 14, boxShadow: "0 2px 10px rgba(0,0,0,0.06)" }}>
        <div style={{ display: "grid", gap: 12 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <div style={{ fontWeight: 900, color: "#555", marginBottom: 6 }}>Role</div>
              <select
                value={localRole}
                onChange={(e) => setLocalRole(e.target.value)}
                style={{ width: "100%", padding: 10, borderRadius: 12, border: "1px solid #ddd", background: "#fff" }}
              >
                <option value="student">student</option>
                <option value="teacher">teacher</option>
              </select>
            </div>
            <div>
              <div style={{ fontWeight: 900, color: "#555", marginBottom: 6 }}>User ID</div>
              <input
                value={localId}
                onChange={(e) => setLocalId(e.target.value)}
                placeholder="VD: 1"
                style={{ width: "100%", padding: 10, borderRadius: 12, border: "1px solid #ddd" }}
              />
              {!parsedId ? <div style={{ marginTop: 6, color: "#b15b00", fontSize: 13 }}>User ID phải là số dương.</div> : null}
            </div>
          </div>

          <div>
            <div style={{ fontWeight: 900, color: "#555", marginBottom: 6 }}>Tên hiển thị (tuỳ chọn)</div>
            <input
              value={localName}
              onChange={(e) => setLocalName(e.target.value)}
              placeholder="VD: Nguyễn Văn A"
              style={{ width: "100%", padding: 10, borderRadius: 12, border: "1px solid #ddd" }}
            />
          </div>

          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <button type="submit" disabled={!parsedId} style={{ padding: "10px 14px" }}>
              Đăng nhập
            </button>
            <span style={{ color: "#666" }}>
              Tip: teacher demo thường là ID=1.
            </span>
          </div>
        </div>
      </form>
    </div>
  );
}
