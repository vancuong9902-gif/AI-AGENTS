import React from 'react';
import Alert from '../components/Alert';
import { authApi, getErrorMessage } from '../api';
import { useAuth } from '../auth';

export default function RegisterPage({ navigate }) {
  const { login } = useAuth();
  const [form, setForm] = React.useState({ name: '', email: '', password: '', role: 'student' });
  const [error, setError] = React.useState('');
  const [loading, setLoading] = React.useState(false);

  const update = (key, val) => setForm((p) => ({ ...p, [key]: val }));

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!form.name.trim() || !form.email.trim() || !form.password.trim()) {
      setError('Vui lòng điền đầy đủ thông tin.');
      return;
    }
    if (form.password.length < 6) {
      setError('Mật khẩu phải có ít nhất 6 ký tự.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const res = await authApi.register(form);
      const data = res.data.data;
      await login(data.token?.access_token, data.user);
      navigate(data.user.role === 'teacher' ? '/teacher' : '/student');
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
        <h2 className="auth-title">Tạo tài khoản</h2>
        <p className="auth-sub">Chọn vai trò của bạn để bắt đầu</p>

        <Alert type="error" message={error} />

        <form onSubmit={onSubmit} className="stack" style={{ gap: 14 }}>
          <div className="form-group">
            <label>Bạn là:</label>
            <div className="role-selector">
              {[
                { value: 'teacher', icon: '👩‍🏫', label: 'Giáo viên', desc: 'Tải tài liệu, quản lý lớp' },
                { value: 'student', icon: '👨‍🎓', label: 'Học sinh', desc: 'Học bài, làm kiểm tra' },
              ].map((r) => (
                <div
                  key={r.value}
                  className={`role-option ${form.role === r.value ? 'selected' : ''}`}
                  onClick={() => update('role', r.value)}
                >
                  <div className="role-icon">{r.icon}</div>
                  <div className="role-label">{r.label}</div>
                  <div className="role-desc">{r.desc}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label>Họ tên</label>
            <input placeholder="Nguyễn Văn A" value={form.name} onChange={(e) => update('name', e.target.value)} required />
          </div>
          <div className="form-group">
            <label>Email</label>
            <input type="email" placeholder="email@example.com" value={form.email} onChange={(e) => update('email', e.target.value)} required />
          </div>
          <div className="form-group">
            <label>Mật khẩu</label>
            <input type="password" placeholder="Ít nhất 6 ký tự" value={form.password} onChange={(e) => update('password', e.target.value)} required />
          </div>

          <button type="submit" disabled={loading} style={{ marginTop: 4 }}>
            {loading ? '⏳ Đang tạo...' : '✅ Tạo tài khoản'}
          </button>
        </form>

        <div className="auth-footer">
          Đã có tài khoản?{' '}
          <button className="link" onClick={() => navigate('/login')}>Đăng nhập</button>
        </div>
      </div>
    </div>
  );
}
