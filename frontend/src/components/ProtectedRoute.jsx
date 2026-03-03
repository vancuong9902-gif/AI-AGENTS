import React from 'react';
import { useAuth } from '../context/AuthContext';

export default function ProtectedRoute({ role, navigate, children }) {
  const { isAuthenticated, user, authEnabled } = useAuth();

  React.useEffect(() => {
    if (!isAuthenticated && authEnabled) {
      navigate('/login', true);
      return;
    }

    const currentRole = user?.role || 'student';
    if (role && currentRole !== role) {
      navigate(currentRole === 'teacher' ? '/teacher/dashboard' : '/student/dashboard', true);
    }
  }, [authEnabled, isAuthenticated, navigate, role, user?.role]);

  if (!isAuthenticated && authEnabled) return null;
  if (role && user?.role && user.role !== role) return null;

  return children;
}
