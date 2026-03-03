import React from 'react';
import Alert from '../components/Alert';
import { authApi, getErrorMessage } from '../api';
import { useAuth } from '../context/AuthContext';

export default function LoginPage({ navigate }) {
  const { login, authEnabled } = useAuth();
  const [form, setForm] = React.useState({ email: '', password: '' });
  const [error, setError] = React.useState('');
  const [loading, setLoading] = React.useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (authEnabled) {
        const res = await authApi.login({ email: form.email.trim().toLowerCase(), password: form.password });
        const data = res.data;
        login(data.access_token, data.user);

        if (data.user?.role === 'teacher') {
          navigate('/teacher/dashboard', true);
        } else {
          navigate('/student/dashboard', true);
        }
      } else {
        const role = form.email.toLowerCase().includes('teacher') ? 'teacher' : 'student';
        const fallbackUser = {
          id: 0,
          email: form.email.trim().toLowerCase(),
          full_name: 'Demo User',
          role,
        };
        login('auth-disabled', fallbackUser);
        navigate(role === 'teacher' ? '/teacher/dashboard' : '/student/dashboard', true);
      }
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <h2 className="auth-title">Đăng nhập</h2>
        <Alert type="error" message={error} />

        <form onSubmit={onSubmit} className="stack auth-form">
          <div className="form-group">
            <label>Email</label>
            <input type="email" value={form.email} onChange={(e) => setForm((prev) => ({ ...prev, email: e.target.value }))} required />
          </div>

          <div className="form-group">
            <label>Mật khẩu</label>
            <input type="password" value={form.password} onChange={(e) => setForm((prev) => ({ ...prev, password: e.target.value }))} required />
          </div>

          <button type="submit" disabled={loading}>{loading ? 'Đang đăng nhập...' : 'Đăng nhập'}</button>
        </form>
      </div>
    </div>
  );
}
