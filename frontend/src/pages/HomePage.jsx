import React from 'react';
import { healthApi } from '../api';
import { useAuth } from '../auth';

export default function HomePage({ navigate }) {
  const { isLoggedIn, user } = useAuth();
  const [health, setHealth] = React.useState('checking');

  React.useEffect(() => {
    if (isLoggedIn && user?.role) {
      navigate(user.role === 'teacher' ? '/teacher' : '/student', true);
    }
  }, [isLoggedIn, user, navigate]);

  React.useEffect(() => {
    let mounted = true;
    healthApi
      .check()
      .then(() => mounted && setHealth('online'))
      .catch(() => mounted && setHealth('offline'));
    return () => {
      mounted = false;
    };
  }, []);

  const runDemo = (role) => {
    localStorage.removeItem('token');
    localStorage.setItem('userId', '1');
    localStorage.setItem('userRole', role);
    localStorage.setItem('userEmail', `${role}@demo.local`);
    localStorage.setItem('userName', `Demo ${role}`);
    navigate(role === 'teacher' ? '/teacher' : '/student');
    window.location.reload();
  };

  return (
    <div className="shell">
      <div className="card stack">
        <h1>AI LMS</h1>
        <p className={`health ${health}`}>Status: {health === 'checking' ? 'Checking...' : health}</p>
        <div className="row">
          <button onClick={() => navigate('/login')}>Login</button>
          <button className="ghost" onClick={() => navigate('/register')}>Register</button>
        </div>
        <button className="link" onClick={() => runDemo('teacher')}>Demo nhanh (Teacher)</button>
        <button className="link" onClick={() => runDemo('student')}>Demo nhanh (Student)</button>
      </div>
    </div>
  );
}
