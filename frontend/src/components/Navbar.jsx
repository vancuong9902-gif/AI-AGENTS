import React from 'react';
import { useAuth } from '../auth';

export default function Navbar({ path, navigate }) {
  const { user, isLoggedIn, logout } = useAuth();

  if (path === '/login' || path === '/register') return null;

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  return (
    <nav className="navbar">
      <button className="link logo" onClick={() => navigate('/')}>AI LMS</button>
      {isLoggedIn ? (
        <div className="nav-right">
          <span>Xin chào, {user?.full_name || user?.email || 'Demo User'}</span>
          <span className={`badge role ${user?.role || 'student'}`}>{user?.role || 'student'}</span>
          <button onClick={handleLogout}>Logout</button>
        </div>
      ) : (
        <div className="nav-right">
          <button className="link" onClick={() => navigate('/login')}>Login</button>
          <button className="link" onClick={() => navigate('/register')}>Register</button>
        </div>
      )}
    </nav>
  );
}
