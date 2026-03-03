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
  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  const onSubmit = async (e) => {
    e.preventDefault();

    const payload = {
      name: form.name.trim(),
      email: form.email.trim().toLowerCase(),
      password: form.password,
      role: String(form.role || 'student').toLowerCase(),
    };

    if (!payload.name || !payload.email || !payload.password.trim()) {
      setError('Vui lòng điền đầy đủ thông tin.');
      return;
    }
    if (payload.password.length < 8) {
      setError('Mật khẩu phải có ít nhất 8 ký tự.');
      return;
    }
    if (!emailPattern.test(payload.email)) {
      setError('Email không hợp lệ.');
      return;
    }
    if (!['student', 'teacher'].includes(payload.role)) {
      setError('Vai trò không hợp lệ.');
      return;
    }

    setError('');
    setLoading(true);
    try {
      const registerRes = await authApi.register(payload);
      const registerData = registerRes.data?.data || registerRes.data;

      let token = registerData?.token?.access_token || registerData?.token;
      let user = registerData?.user;

      if (!token || !user) {
        const loginRes = await authApi.login({ email: payload.email, password: payload.password });
        const loginData = loginRes.data?.data || loginRes.data;
        token = token || loginData?.token?.access_token || loginData?.access_token || loginData?.token;
        user = user || loginData?.user;

        if (!user) {
          const meRes = await authApi.me();
          user = meRes.data?.data || meRes.data;
        }
      }

      if (!token || !user) {
        throw new Error('Không thể tự động đăng nhập sau khi đăng ký.');
      }

      await login(token, user);
      navigate(String(user.role).toLowerCase() === 'teacher' ? '/teacher' : '/student');
    } catch (err) {
      if (err.response?.status === 409) {
        setError('Email đã tồn tại, vui lòng dùng email khác.');
        return;
      }
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

        <form onSubmit={onSubmit} className="stack auth-form">
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
            <input type="email" placeholder="email@example.com" value={form.email} onChange={(e) => update('email', e.target.value)} required pattern="[^\s@]+@[^\s@]+\.[^\s@]+" />
          </div>
          <div className="form-group">
            <label>Mật khẩu</label>
            <input type="password" placeholder="Ít nhất 8 ký tự" value={form.password} onChange={(e) => update('password', e.target.value)} required minLength={8} />
          </div>

          <button type="submit" disabled={loading} className="auth-submit-btn">
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
