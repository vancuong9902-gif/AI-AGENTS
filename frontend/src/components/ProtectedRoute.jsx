import React from 'react';
import { useAuth } from '../auth';
import LoadingSpinner from './LoadingSpinner';

export default function ProtectedRoute({ role, navigate, children }) {
  const { user, isLoading, isLoggedIn } = useAuth();

  React.useEffect(() => {
    if (isLoading) return;
    if (!isLoggedIn) {
      navigate('/login');
      return;
    }
    if (role && user?.role !== role) {
      navigate(user?.role === 'teacher' ? '/teacher' : '/student');
    }
  }, [isLoading, isLoggedIn, navigate, role, user]);

  if (isLoading) return <LoadingSpinner />;
  if (!isLoggedIn) return null;
  if (role && user?.role !== role) return null;

  return children;
}
