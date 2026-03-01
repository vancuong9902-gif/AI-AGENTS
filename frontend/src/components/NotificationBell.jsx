import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiJson } from '../lib/api';
import { useAuth } from '../context/AuthContext';

export default function NotificationBell() {
  const { role, userId } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const panelRef = useRef(null);

  const unreadCount = useMemo(() => items.filter((n) => !n.is_read).length, [items]);

  const loadNotifications = async () => {
    if (role !== 'student' || !userId) return;
    try {
      const data = await apiJson('/notifications/my');
      setItems(Array.isArray(data) ? data : []);
    } catch {
      setItems([]);
    }
  };

  useEffect(() => {
    loadNotifications();
    const timer = setInterval(loadNotifications, 30000);
    return () => clearInterval(timer);
  }, [role, userId]);

  useEffect(() => {
    const onClickOutside = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    const onEscape = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onClickOutside);
    document.addEventListener('keydown', onEscape);
    return () => {
      document.removeEventListener('mousedown', onClickOutside);
      document.removeEventListener('keydown', onEscape);
    };
  }, []);

  if (role !== 'student') return null;

  const onNotificationClick = async (n) => {
    try {
      await apiJson(`/notifications/${n.id}/mark-read`, { method: 'POST' });
      setItems((prev) => prev.filter((x) => x.id !== n.id));
    } catch {
      // no-op
    }

    const topic = n?.payload_json?.topic || n?.data?.topic;
    if (topic) navigate(`/learning-path?topic=${encodeURIComponent(topic)}`);
    else navigate('/learning-path');
    setOpen(false);
  };

  return (
    <div className='notification-wrap' ref={panelRef}>
      <button
        className='notification-bell focus-ring'
        onClick={() => setOpen((v) => !v)}
        aria-label='Mở danh sách thông báo'
        aria-haspopup='dialog'
        aria-expanded={open}
        aria-controls='notification-panel'
      >
        🔔
        {unreadCount > 0 && <span className='notification-badge'>{unreadCount}</span>}
      </button>

      {open && (
        <div id='notification-panel' className='notification-dropdown' role='dialog' aria-label='Danh sách thông báo'>
          <div className='notification-title'>Thông báo</div>
          {!items.length ? (
            <div className='notification-empty'>Không có thông báo mới.</div>
          ) : (
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
  );
}
