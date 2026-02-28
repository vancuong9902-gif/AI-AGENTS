import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ children, allow }) {
  const { role } = useAuth();

  if (!role) return <Navigate to="/" />;

  if (!allow.includes(role)) {
    return <h2>Bạn không có quyền truy cập trang này</h2>;
  }

  return children;
}
