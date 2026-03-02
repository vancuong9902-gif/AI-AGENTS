import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/useAuth';
import AuthCard from '../components/AuthCard';
import { loginApi } from '../services/api';

function resolveAuthPayload(data) {
  const token = data?.token?.access_token || data?.token || data?.access_token || data?.data?.token?.access_token || data?.data?.token || data?.data?.access_token;
  const user = data?.user || data?.data?.user || null;
  return { token, user };
}

export default function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [form, setForm] = useState({ email: '', password: '' });
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const onSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      const response = await loginApi(form);
      const { token, user } = resolveAuthPayload(response);

      if (!token || !user?.role) {
        setError('Phản hồi đăng nhập không hợp lệ.');
        return;
      }

      login({ token, user });

      if (user.role === 'admin') navigate('/admin/dashboard');
      else if (user.role === 'teacher') navigate('/teacher/dashboard');
      else navigate('/student/dashboard');
    } catch (apiError) {
      if (apiError.status === 401) {
        setError('Sai email hoặc mật khẩu');
      } else {
        setError(apiError.message || 'Đăng nhập thất bại');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthCard
      title='Đăng nhập LMS'
      subtitle='Sử dụng email và mật khẩu để truy cập hệ thống.'
      footer={<p>Chưa có tài khoản? <Link to='/register'>Đăng ký</Link></p>}
    >
      <form className='auth-form' onSubmit={onSubmit}>
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
        <button type='submit' disabled={isLoading}>{isLoading ? 'Đang xử lý...' : 'Đăng nhập'}</button>
      </form>
    </AuthCard>
  );
}
