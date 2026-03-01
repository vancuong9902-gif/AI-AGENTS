import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { FiLogOut, FiMenu, FiX } from 'react-icons/fi';
import Navbar from './components/Navbar';
import AppRoutes from './routes/AppRoutes';
import NotificationBell from './components/NotificationBell';
import { useAuth } from './context/AuthContext';
import './App.css';

const PAGE_META = [
  { match: /^\/$/, title: 'Đăng nhập', subtitle: 'Thiết lập vai trò và bắt đầu phiên làm việc' },
  { match: /^\/classrooms/, title: 'Lớp học', subtitle: 'Theo dõi lớp học và bài tập hiện có' },
  { match: /^\/assessments/, title: 'Bài đánh giá', subtitle: 'Thực hiện và theo dõi kết quả đánh giá' },
  { match: /^\/learning-path/, title: 'Lộ trình học', subtitle: 'Lộ trình học cá nhân hóa theo năng lực' },
  { match: /^\/tutor/, title: 'Trợ giảng AI', subtitle: 'Hỏi đáp học tập nhanh và rõ ràng' },
  { match: /^\/analytics/, title: 'Phân tích học tập', subtitle: 'Tổng quan tiến độ và mức độ thành thạo' },
  { match: /^\/teacher\//, title: 'Không gian giáo viên', subtitle: 'Quản lý lớp học, tài liệu và phân tích' },
  { match: /^\/upload/, title: 'Tải lên tài liệu', subtitle: 'Đưa tài liệu vào hệ thống để xử lý' },
  { match: /^\/health/, title: 'Trạng thái hệ thống', subtitle: 'Kiểm tra nhanh dịch vụ đang hoạt động' },
];

function App() {
  const { role, userId, fullName, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  const pageMeta = useMemo(
    () => PAGE_META.find((item) => item.match.test(location.pathname)) || { title: 'AI-AGENTS LMS', subtitle: 'Nền tảng học tập thông minh' },
    [location.pathname],
  );

  const displayName = fullName || `Người dùng #${userId ?? 1}`;

  return (
    <div className='app-shell'>
      <aside className={`sidebar ${open ? 'open' : ''}`}>
        <Navbar onNavigate={() => setOpen(false)} />
      </aside>
      {open ? <button type='button' className='sidebar-overlay' aria-label='Đóng menu điều hướng' onClick={() => setOpen(false)} /> : null}
      <div className='main-wrap'>
        <header className='topbar'>
          <div className='topbar-inner'>
            <div className='topbar-heading'>
              <button
                type='button'
                className='nav-toggle focus-ring'
                aria-label={open ? 'Đóng menu' : 'Mở menu'}
                onClick={() => setOpen((v) => !v)}
              >
                {open ? <FiX /> : <FiMenu />}
              </button>
              <div>
                <h1 className='topbar-title'>{pageMeta.title}</h1>
                <p className='topbar-subtitle'>{pageMeta.subtitle}</p>
              </div>
            </div>
            <div className='topbar-actions'>
              <NotificationBell />
              <div className='user-pill'>
                <strong>{displayName}</strong>
                <span>{role === 'teacher' ? 'Giáo viên' : role === 'student' ? 'Học viên' : 'Khách'}</span>
              </div>
              <button type='button' className='logout-btn focus-ring' onClick={() => { logout(); navigate('/'); }}>
                <FiLogOut /> Đăng xuất
              </button>
            </div>
          </div>
        </header>
        <main className='page-content'>
          <AppRoutes />
        </main>
      </div>
    </div>
  );
}

export default App;
