import { createContext, useContext, useEffect, useState } from "react";

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [role, setRole] = useState(() => localStorage.getItem("role") || null); // "student" | "teacher"
  const [userId, setUserId] = useState(() => {
    const v = localStorage.getItem("user_id");
    const n = v ? Number(v) : 1;
    return Number.isFinite(n) ? n : 1;
  });

  const [fullName, setFullName] = useState(() => localStorage.getItem("full_name") || null);

  useEffect(() => {
    if (role) localStorage.setItem("role", role);
    else localStorage.removeItem("role");
  }, [role]);

  useEffect(() => {
    localStorage.setItem("user_id", String(userId ?? 1));
  }, [userId]);

  useEffect(() => {
    if (fullName) localStorage.setItem("full_name", fullName);
    else localStorage.removeItem("full_name");
  }, [fullName]);

  const logout = () => {
    setFullName(null);
    setRole(null);
    // keep userId as-is for demo convenience
  };

  return (
    <AuthContext.Provider value={{ role, setRole, userId, setUserId, fullName, setFullName, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
