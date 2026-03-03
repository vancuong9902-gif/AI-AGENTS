import React from 'react';
import Alert from '../components/Alert';
import { authApi, getErrorMessage } from '../api';
import { useAuth } from '../context/AuthContext';

export default function RegisterPage({ navigate }) {
  const { authEnabled } = useAuth();
  const [form, setForm] = React.useState({
    fullName: '',
    email: '',
    password: '',
    confirmPassword: '',
    role: 'student',
  });
  const [error, setError] = React.useState('');
  const [loading, setLoading] = React.useState(false);

  const update = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));
  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  const onSubmit = async (e) => {
    e.preventDefault();

    const payload = {
      full_name: form.fullName.trim(),
      email: form.email.trim().toLowerCase(),
      password: form.password,
      role: form.role,
    };

    if (!payload.full_name || !payload.email || !payload.password || !form.confirmPassword) {
      setError('Vui lòng điền đầy đủ thông tin.');
      return;
    }
    if (!emailPattern.test(payload.email)) {
      setError('Email không hợp lệ.');
      return;
    }
    if (payload.password.length < 8) {
      setError('Mật khẩu phải có ít nhất 8 ký tự.');
      return;
    }
    if (payload.password !== form.confirmPassword) {
      setError('Mật khẩu xác nhận không khớp.');
      return;
    }

    setError('');
    setLoading(true);
    try {
      if (authEnabled) {
        await authApi.register(payload);
      }
      navigate('/login', true);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <h2 className="auth-title">Đăng ký</h2>
        <Alert type="error" message={error} />

        <form onSubmit={onSubmit} className="stack auth-form">
          <div className="form-group">
            <label>Họ tên</label>
            <input value={form.fullName} onChange={(e) => update('fullName', e.target.value)} required />
          </div>

          <div className="form-group">
            <label>Email</label>
            <input type="email" value={form.email} onChange={(e) => update('email', e.target.value)} required />
          </div>

          <div className="form-group">
            <label>Mật khẩu</label>
            <input type="password" value={form.password} onChange={(e) => update('password', e.target.value)} required minLength={8} />
          </div>

          <div className="form-group">
            <label>Xác nhận mật khẩu</label>
            <input type="password" value={form.confirmPassword} onChange={(e) => update('confirmPassword', e.target.value)} required minLength={8} />
          </div>

          <div className="form-group">
            <label>Vai trò</label>
            <select value={form.role} onChange={(e) => update('role', e.target.value)}>
              <option value="teacher">Giáo viên</option>
              <option value="student">Học sinh</option>
            </select>
          </div>

          <button type="submit" disabled={loading}>
            {loading ? 'Đang đăng ký...' : 'Đăng ký'}
          </button>
        </form>
      </div>
    </div>
  );
}
