import React from 'react';
import Alert from '../components/Alert';
import { authApi, getErrorMessage } from '../api';
import { useAuth } from '../auth';

export default function LoginPage({ navigate }) {
  const { login } = useAuth();
  const [form, setForm] = React.useState({ email: '', password: '' });
  const [error, setError] = React.useState('');
  const [loading, setLoading] = React.useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await authApi.login(form);
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

        <form onSubmit={onSubmit} className="stack" style={{ gap: 14 }}>
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
          <button type="submit" disabled={loading}>
            {loading ? '⏳ Đang đăng nhập...' : '🔑 Đăng nhập'}
          </button>
        </form>

        <div className="auth-footer">
          Chưa có tài khoản?{' '}
          <button className="link" onClick={() => navigate('/register')}>Đăng ký ngay</button>
        </div>
      </div>
    </div>
  );
}
