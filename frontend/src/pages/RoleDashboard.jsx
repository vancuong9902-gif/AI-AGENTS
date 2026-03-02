import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/useAuth';

export default function RoleDashboard({ role }) {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const roleLabel = role === 'admin' ? 'Admin' : role === 'teacher' ? 'Teacher' : 'Student';

  return (
    <div className='auth-shell'>
      <div className='auth-card'>
        <h1>{roleLabel} Dashboard</h1>
        <p className='auth-subtitle'>Xin chào {user?.name || user?.full_name || user?.email || 'người dùng'}.</p>
        <p className='auth-note'>Đăng nhập thành công với quyền {roleLabel.toLowerCase()}.</p>
        <button
          type='button'
          onClick={() => {
            logout();
            navigate('/login');
          }}
        >
          Đăng xuất
        </button>
      </div>
    </div>
  );
}
