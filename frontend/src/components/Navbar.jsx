import { NavLink } from 'react-router-dom';
import { FiActivity, FiBarChart2, FiBookOpen, FiClipboard, FiFolder, FiHome, FiLayers, FiUploadCloud, FiUsers } from 'react-icons/fi';
import { useAuth } from '../context/AuthContext';

const student = [
  { to: '/classrooms', label: 'Lớp học', icon: FiUsers },
  { to: '/assessments', label: 'Bài đánh giá', icon: FiClipboard },
  { to: '/learning-path', label: 'Lộ trình học', icon: FiLayers },
  { to: '/quiz', label: 'Bài kiểm tra đầu vào', icon: FiBookOpen },
  { to: '/tutor', label: 'Trợ giảng AI', icon: FiHome },
  { to: '/analytics', label: 'Phân tích học tập', icon: FiBarChart2 },
];

const teacher = [
  { to: '/upload', label: 'Tải lên tài liệu', icon: FiUploadCloud },
  { to: '/teacher/files', label: 'Thư viện tài liệu', icon: FiFolder },
  { to: '/teacher/classrooms', label: 'Lớp học', icon: FiUsers },
  { to: '/teacher/assessments', label: 'Bài đánh giá', icon: FiClipboard },
  { to: '/teacher/progress', label: 'Tiến độ', icon: FiBookOpen },
  { to: '/teacher/analytics', label: 'Phân tích học tập', icon: FiBarChart2 },
  { to: '/teacher/infra', label: 'Hạ tầng', icon: FiActivity },
];

export default function Navbar({ onNavigate }) {
  const { role } = useAuth();
  const navItems = role === 'teacher' ? teacher : role === 'student' ? student : [];

  return (
    <div className='sidebar-content'>
      <div className='brand'>
        <span className='brand-badge'>🎓</span>
        <div>
          <strong>AI-AGENTS LMS</strong>
          <p>Nền tảng học tập thông minh</p>
        </div>
      </div>

      <div className='nav-group-label'>{role === 'teacher' ? 'Không gian giáo viên' : 'Không gian học viên'}</div>
      <nav className='nav-section'>
        <NavLink onClick={onNavigate} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} to='/'>
          <FiHome /> Đăng nhập
        </NavLink>
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink onClick={onNavigate} key={to} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} to={to}>
            <Icon /> {label}
          </NavLink>
        ))}
        <NavLink onClick={onNavigate} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} to='/health'>
          <FiActivity /> Trạng thái hệ thống
        </NavLink>
      </nav>
    </div>
  );
}
