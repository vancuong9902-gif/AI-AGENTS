import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/useAuth';

export default function ProtectedRoute({ allowedRoles, children }) {
  const { token, role } = useAuth();

  if (!token) {
    return <Navigate to='/login' replace />;
  }

  if (allowedRoles && !allowedRoles.includes(role)) {
    return <Navigate to='/login' replace />;
  }

  return children;
}
