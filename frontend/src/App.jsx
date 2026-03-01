import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { FiLogOut, FiMenu, FiMoon, FiSearch, FiSun, FiX } from 'react-icons/fi';
import Navbar from './components/Navbar';
import AppRoutes from './routes/AppRoutes';
import NotificationBell from './components/NotificationBell';
import { useAuth } from './context/useAuth';
import './App.css';

const PAGE_META = [
  { match: /^\/$/, title: 'Đăng nhập', subtitle: 'Thiết lập vai trò và bắt đầu phiên làm việc' },
  { match: /^\/home/, title: 'Trang chủ', subtitle: 'Tổng quan khóa học, tiến độ và tác vụ quan trọng' },
  { match: /^\/classrooms/, title: 'Lớp học', subtitle: 'Theo dõi lớp học và bài tập hiện có' },
  { match: /^\/assessments/, title: 'Kiểm tra & Quiz', subtitle: 'Thực hiện bài kiểm tra trực tuyến và theo dõi kết quả' },
  { match: /^\/learning-path/, title: 'Lộ trình học', subtitle: 'Lộ trình học cá nhân hóa theo năng lực' },
  { match: /^\/tutor/, title: 'Trợ giảng AI', subtitle: 'Hỏi đáp học tập nhanh và rõ ràng' },
  { match: /^\/analytics/, title: 'Dashboard phân tích', subtitle: 'Biểu đồ điểm số, tiến độ và mức độ tham gia học tập' },
  { match: /^\/teacher\//, title: 'Không gian giáo viên', subtitle: 'Quản lý lớp học, tài liệu và phân tích' },
  { match: /^\/upload/, title: 'Tải lên tài liệu', subtitle: 'Đưa tài liệu vào hệ thống để xử lý' },
  { match: /^\/health/, title: 'Trạng thái hệ thống', subtitle: 'Kiểm tra nhanh dịch vụ đang hoạt động' },
];

function App() {
  const { role, userId, fullName, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'system');
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return undefined;
    const onEscape = (event) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };
    document.addEventListener('keydown', onEscape);
    return () => document.removeEventListener('keydown', onEscape);
  }, [open]);

  useEffect(() => {
    if (window.innerWidth > 960) return undefined;
    document.body.style.overflow = open ? 'hidden' : '';
    return () => {
      document.body.style.overflow = '';
    };
  }, [open]);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'system') {
      root.removeAttribute('data-theme');
      localStorage.removeItem('theme');
      return;
    }
    root.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const pageMeta = useMemo(
    () => PAGE_META.find((item) => item.match.test(location.pathname)) || { title: 'AI-AGENTS LMS', subtitle: 'Nền tảng học tập thông minh' },
    [location.pathname],
  );

  const displayName = fullName || `Người dùng #${userId ?? 1}`;

  const handleGlobalSearch = (event) => {
    event.preventDefault();
    if (!search.trim()) return;
    navigate(`/topic-selection?query=${encodeURIComponent(search.trim())}`);
    setSearch('');
  };

  const handleThemeToggle = () => {
    setTheme((prev) => {
      if (prev === 'light') return 'dark';
      if (prev === 'dark') return 'system';
      return 'light';
    });
  };

  const themeLabel = theme === 'dark' ? 'Chế độ tối' : theme === 'light' ? 'Chế độ sáng' : 'Theo hệ thống';

  return (
    <div className='app-shell'>
      <aside id='app-sidebar' className={`sidebar ${open ? 'open' : ''}`} aria-label='Thanh điều hướng chính'>
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
                aria-controls='app-sidebar'
                aria-expanded={open}
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
              <form className='global-search' onSubmit={handleGlobalSearch} role='search' aria-label='Tìm kiếm khóa học và tài liệu'>
                <FiSearch aria-hidden='true' />
                <input
                  type='search'
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder='Tìm khóa học, bài học, tài liệu...'
                />
              </form>
              <button type='button' className='theme-btn focus-ring' onClick={handleThemeToggle} title={themeLabel} aria-label={themeLabel}>
                {theme === 'dark' ? <FiMoon /> : <FiSun />}
                <span>{themeLabel}</span>
              </button>
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
        <footer className='app-footer'>
          <div className='container app-footer-inner'>
            <p>© {new Date().getFullYear()} AI-AGENTS LMS · Học tập hiệu quả trên mọi thiết bị.</p>
            <p>Chuẩn truy cập, tối ưu SEO cơ bản và trải nghiệm nhất quán Light/Dark mode.</p>
          </div>
        </footer>
      </div>
    </div>
  );
}

export default App;
