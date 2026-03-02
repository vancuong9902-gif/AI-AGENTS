import React from 'react';
import { useAuth } from '../auth';
import { mvpApi } from '../api';

export default function Navbar({ path, navigate }) {
  const { user, isLoggedIn, logout } = useAuth();
  const [notifCount, setNotifCount] = React.useState(0);

  React.useEffect(() => {
    if (!isLoggedIn) return;
    mvpApi.getNotifications().then((r) => {
      const unread = (r.data.notifications || r.data || []).filter((n) => !n.is_read).length;
      setNotifCount(unread);
    }).catch(() => {});
  }, [isLoggedIn]);

  if (path === '/login' || path === '/register') return null;

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const dashboardPath = user?.role === 'teacher' ? '/teacher' : '/student';

  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <button className="logo" onClick={() => navigate(isLoggedIn ? dashboardPath : '/')}>
          🎓 AI<span>LMS</span>
        </button>
        {isLoggedIn && (
          <span className={`badge role ${user?.role || 'student'}`} style={{ marginLeft: 4 }}>
            {user?.role === 'teacher' ? '👩‍🏫 Giáo viên' : '👨‍🎓 Học sinh'}
          </span>
        )}
      </div>

      {isLoggedIn ? (
        <div className="nav-right">
          {notifCount > 0 && (
            <div className="nav-notifications">
              <button className="ghost sm" title="Thông báo">
                🔔
                <span className="notif-dot" />
              </button>
            </div>
          )}
          <span className="nav-user">
            👤 {user?.full_name || user?.email || 'Người dùng'}
          </span>
          <button className="danger sm" onClick={handleLogout}>
            🚪 Đăng xuất
          </button>
        </div>
      ) : (
        <div className="nav-right">
          <button className="ghost sm" onClick={() => navigate('/login')}>Đăng nhập</button>
          <button className="sm" onClick={() => navigate('/register')}>Đăng ký</button>
        </div>
      )}
    </nav>
  );
}
