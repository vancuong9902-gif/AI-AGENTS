import React from 'react';
import Alert from '../components/Alert';
import { authApi, getErrorMessage } from '../api';
import { useAuth } from '../auth';

export default function LoginPage({ navigate }) {
  const { login } = useAuth();
  const [form, setForm] = React.useState({ email: '', password: '' });
  const [selectedRole, setSelectedRole] = React.useState('student');
  const [error, setError] = React.useState('');
  const [loading, setLoading] = React.useState(false);

  const handleSubmit = async (payload) => {
    setError('');
    setLoading(true);
    try {
      const res = await authApi.login(payload || { ...form, role: selectedRole });
      const data = res.data.data || res.data;
      const token = data.token?.access_token || data.access_token;
      const user = data.user || data;
      await login(token, user);
      navigate(user.role === 'teacher' ? '/teacher' : '/student');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    await handleSubmit({ ...form, role: selectedRole });
  };

  const quickLogin = async (role) => {
    const demo = { email: 'cuong0505@gmail.com', password: 'cuong0505', role };
    setForm({ email: demo.email, password: demo.password });
    setSelectedRole(role);
    await handleSubmit(demo);
  };

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <div className="auth-logo">
          <h1>🎓 AI LMS</h1>
          <p>Hệ thống học tập thông minh</p>
        </div>
        <h2 className="auth-title">Đăng nhập</h2>
        <p className="auth-sub">Chào mừng trở lại!</p>

        <Alert type="error" message={error} />

        <form onSubmit={onSubmit} className="stack auth-form">
          <div className="form-group">
            <label>Email</label>
            <input type="email" placeholder="email@example.com" value={form.email}
              onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))} required />
          </div>
          <div className="form-group">
            <label>Mật khẩu</label>
            <input type="password" placeholder="••••••••" value={form.password}
              onChange={(e) => setForm((p) => ({ ...p, password: e.target.value }))} required />
          </div>
          <div className="form-group">
            <label>Bạn đăng nhập với tư cách?</label>
            <select value={selectedRole} onChange={(e) => setSelectedRole(e.target.value)}>
              <option value="teacher">Giáo viên</option>
              <option value="student">Học viên</option>
            </select>
          </div>
          <button type="submit" disabled={loading}>
            {loading ? '⏳ Đang đăng nhập...' : '🔑 Đăng nhập'}
          </button>
        </form>

        <div className="demo-section">
          <p className="demo-label">🎯 Dùng thử ngay (không cần đăng ký)</p>
          <div className="demo-buttons">
            <button
              className="btn-demo btn-teacher"
              onClick={() => quickLogin('teacher')}
              disabled={loading}
              type="button"
            >
              👩‍🏫 Đăng nhập Demo Giáo viên
            </button>
            <button
              className="btn-demo btn-student"
              onClick={() => quickLogin('student')}
              disabled={loading}
              type="button"
            >
              👨‍🎓 Đăng nhập Demo Học viên
            </button>
          </div>
          <p className="demo-hint">Email: cuong0505@gmail.com | Mật khẩu: cuong0505</p>
        </div>

        <div className="auth-footer">
          Chưa có tài khoản?{' '}
          <button className="link" onClick={() => navigate('/register')}>Đăng ký ngay</button>
        </div>
      </div>
    </div>
  );
}
