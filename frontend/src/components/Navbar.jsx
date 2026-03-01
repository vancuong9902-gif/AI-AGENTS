import { useEffect, useMemo, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { apiJson } from '../lib/api';

export default function Navbar({ onNavigate }) {
  const { role, userId, logout } = useAuth();
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const nav = useNavigate();

  const student = [
    ['/classrooms', 'Lớp học'], ['/assessments', 'Bài tổng hợp'], ['/learning-path', 'Learning Path'], ['/quiz', 'Placement Quiz'], ['/tutor', 'Tutor AI'], ['/analytics', 'Analytics'], ['/agent-flow', 'Agent Flow'],
  ];
  const teacher = [
    ['/upload', 'Upload'], ['/teacher/files', 'Thư viện tài liệu'], ['/teacher/classrooms', 'Lớp học'], ['/teacher/assessments', 'Quản lý bài'], ['/teacher/progress', 'Progress'], ['/teacher/analytics', 'Analytics'], ['/teacher/infra', 'Infra'],
  ];
  const navItems = role === 'teacher' ? teacher : role === 'student' ? student : [];

  const unreadCount = useMemo(() => items.filter((x) => !x.is_read).length, [items]);

  useEffect(() => {
    if (role !== 'teacher' || !userId) return undefined;
    const poll = async () => {
      try {
        const res = await apiJson('/notifications/my');
        const payload = res?.data || res || {};
        setItems(Array.isArray(payload.items) ? payload.items : []);
      } catch {
        setItems([]);
      }
    };
    poll();
    const interval = setInterval(poll, 30000);
    return () => clearInterval(interval);
  }, [role, userId]);

  const onNotificationClick = async (n) => {
    try {
      await apiJson(`/notifications/${n.id}/mark-read`, { method: 'POST' });
      setItems((prev) => prev.map((it) => (it.id === n.id ? { ...it, is_read: true } : it)));
    } catch {
      // ignore
    }
    const cid = n?.payload_json?.classroom_id;
    if (cid) nav(`/teacher/analytics?classroomId=${encodeURIComponent(cid)}`);
    setOpen(false);
  };

  return (
    <>
      <div className='brand'>🎓 AI-Agents LMS</div>
      <div className='nav-group-label'>{role === 'teacher' ? 'Teacher' : 'Student'}</div>
      <div className='nav-section'>
        <NavLink onClick={onNavigate} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} to='/'>Đăng nhập</NavLink>
        {navItems.map(([to, label]) => <NavLink onClick={onNavigate} key={to} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} to={to}>{label}</NavLink>)}
        <NavLink onClick={onNavigate} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} to='/health'>Health</NavLink>
      </div>
      <div style={{ marginTop: 16, fontSize: 13, color: 'var(--muted)' }}>Role: <b>{role || 'guest'}</b> · User ID: <b>{userId ?? 1}</b></div>

      {role === 'teacher' && (
        <div className='notification-wrap' style={{ marginTop: 8 }}>
          <button className='notification-bell' onClick={() => setOpen((v) => !v)} aria-label='Teacher notifications'>🔔{unreadCount > 0 && <span className='notification-badge'>{unreadCount}</span>}</button>
          {open && (
            <div className='notification-dropdown'>
              <div className='notification-title'>Thông báo giáo viên</div>
              {!items.length ? <div className='notification-empty'>Chưa có thông báo.</div> : (
                <div className='notification-list'>
                  {items.map((n) => (
                    <button key={n.id} className='notification-item' onClick={() => onNotificationClick(n)}>
                      <div className='notification-item-title'>{n.title}</div>
                      <div className='notification-item-message'>{n.message}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <button aria-label='Đăng xuất' className='logout-btn focus-ring' style={{ marginTop: 10 }} onClick={() => { logout(); nav('/'); onNavigate?.(); }}>Logout</button>
    </>
  );
}
