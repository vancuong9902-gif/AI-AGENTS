import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import AuthCard from '../components/AuthCard';
import { registerApi } from '../services/api';

export default function Register() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: '', email: '', password: '', student_code: '' });
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const onSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await registerApi(form);
      navigate('/login');
    } catch (apiError) {
      const rawMessage = String(apiError?.payload?.message || apiError?.payload?.detail || apiError.message || '').toLowerCase();
      if (apiError.status === 409 || rawMessage.includes('email') || rawMessage.includes('exists')) {
        setError('Email đã được sử dụng');
      } else {
        setError(apiError.message || 'Đăng ký thất bại');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthCard
      title='Tạo tài khoản'
      subtitle='Đăng ký tài khoản mới, mặc định quyền student.'
      footer={<p>Đã có tài khoản? <Link to='/login'>Đăng nhập</Link></p>}
    >
      <form className='auth-form' onSubmit={onSubmit}>
        <label>
          Họ và tên
          <input
            value={form.full_name}
            onChange={(event) => setForm((prev) => ({ ...prev, full_name: event.target.value }))}
            required
          />
        </label>
        <label>
          Mã sinh viên
          <input
            value={form.student_code}
            onChange={(event) => setForm((prev) => ({ ...prev, student_code: event.target.value }))}
            required
          />
        </label>
        <label>
          Email
          <input
            type='email'
            value={form.email}
            onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
            required
          />
        </label>
        <label>
          Mật khẩu
          <input
            type='password'
            value={form.password}
            onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
            required
          />
        </label>
        {error ? <p className='auth-error'>{error}</p> : null}
        <button type='submit' disabled={isLoading}>{isLoading ? 'Đang xử lý...' : 'Đăng ký'}</button>
      </form>
    </AuthCard>
  );
}
