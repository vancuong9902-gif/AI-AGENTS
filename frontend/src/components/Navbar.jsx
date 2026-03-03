import React from 'react';
import { useAuth } from '../auth';
import { mvpApi } from '../api';

export default function Navbar({ path, navigate }) {
  const { user, isLoggedIn, logout } = useAuth();
  const [notifications, setNotifications] = React.useState([]);
  const [open, setOpen] = React.useState(false);

  const loadNotifications = React.useCallback(async () => {
    if (!isLoggedIn) return;
    try {
      const r = await mvpApi.getNotifications();
      const items = r.data.data?.items || r.data.notifications || r.data || [];
      setNotifications(items);
    } catch {
      setNotifications([]);
    }
  }, [isLoggedIn]);

  React.useEffect(() => {
    loadNotifications();
  }, [loadNotifications]);

  if (path === '/login' || path === '/register') return null;

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const markRead = async (id) => {
    try {
      await mvpApi.markNotificationRead(id);
      await loadNotifications();
    } catch {
      // ignore
    }
  };

  const unreadCount = notifications.filter((n) => !n.is_read).length;
  const dashboardPath = user?.role === 'teacher' ? '/teacher/dashboard' : '/student/dashboard';

  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <button className="logo" onClick={() => navigate(isLoggedIn ? dashboardPath : '/')}>
          🎓 AI<span>LMS</span>
        </button>
        {isLoggedIn && (
          <span className={`badge role ${user?.role || 'student'} nav-role-badge`}>
            {user?.role === 'teacher' ? '👩‍🏫 Giáo viên' : '👨‍🎓 Học sinh'}
          </span>
        )}
      </div>

      {isLoggedIn ? (
        <div className="nav-right">
          <div className="nav-notifications">
            <button className="ghost sm" title="Thông báo" onClick={() => setOpen((v) => !v)}>
              🔔
              {unreadCount > 0 && <span className="notif-dot" />}
            </button>
            {open && (
              <div className="notif-dropdown">
                <div className="notif-title">Thông báo</div>
                {notifications.length === 0 ? (
                  <div className="notif-empty">Chưa có thông báo</div>
                ) : (
                  notifications.slice(0, 8).map((n) => (
                    <button key={n.id} className={`notif-item ${n.is_read ? 'read' : 'unread'}`} onClick={() => markRead(n.id)}>
                      <div className="notif-item-title">{n.title || 'Thông báo'}</div>
                      <div className="notif-item-message">{n.message || ''}</div>
                    </button>
                  ))
                )}
              </div>
            )}
          </div>
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
