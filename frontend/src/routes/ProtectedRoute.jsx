import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/useAuth';

function resolveDefaultPath(role) {
  if (role === 'student') return '/student';
  if (role === 'teacher') return '/teacher';
  return '/login';
}

export default function ProtectedRoute({ allowedRoles, children }) {
  const { token, role } = useAuth();

  if (!token) {
    return <Navigate to='/login' replace />;
  }

  if (allowedRoles && !allowedRoles.includes(role)) {
    return <Navigate to={resolveDefaultPath(role)} replace />;
  }

  return children;
}
