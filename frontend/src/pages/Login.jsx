import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/useAuth';
import AuthCard from '../components/AuthCard';
import { loginApi } from '../services/api';

function resolveLoginToken(response) {
  return response?.data?.access_token || response?.access_token || null;
}

function resolveRole(response) {
  return response?.data?.role || response?.role || null;
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
      const token = resolveLoginToken(response);
      const role = resolveRole(response);

      if (!token || !role) {
        setError('Phản hồi đăng nhập không hợp lệ.');
        return;
      }

      const user = {
        email: form.email,
        role,
      };
      login({ token, user });

      if (role === 'student') navigate('/student');
      else if (role === 'teacher') navigate('/teacher');
      else navigate('/login');
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
