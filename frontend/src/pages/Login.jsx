import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/useAuth';
import Card from '../ui/Card';
import Button from '../ui/Button';
import PageHeader from '../ui/PageHeader';
import { apiJson } from '../lib/api';

const DEMO_MODE = String(import.meta?.env?.VITE_DEMO_MODE || 'false').toLowerCase() === 'true';

export default function Login() {
  const navigate = useNavigate();
  const { setRole, setUserId, fullName, setFullName } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [studentCode, setStudentCode] = useState('');
  const [isRegister, setIsRegister] = useState(false);
  const [error, setError] = useState('');

  const saveAuth = (data) => {
    const token = data?.token?.access_token;
    if (token) localStorage.setItem('token', token);
    const user = data?.user || {};
    setUserId(Number(user.id || 1));
    setRole(user.role || 'student');
    setFullName(user.full_name || null);
    localStorage.setItem('role', user.role || 'student');
    navigate('/home');
  };

  const doAuth = async (e) => {
    e.preventDefault();
    setError('');
    try {
      if (isRegister) {
        const data = await apiJson('/auth/register', {
          method: 'POST',
          body: { email, password, full_name: fullName || null, student_code: studentCode },
        });
        saveAuth(data);
      } else {
        const data = await apiJson('/auth/login-json', { method: 'POST', body: { email, password } });
        saveAuth(data);
      }
    } catch (err) {
      setError(err?.message || 'Đăng nhập thất bại');
    }
  };

  const runDemo = (role) => {
    localStorage.removeItem('token');
    setRole(role);
    setUserId(role === 'teacher' ? 1 : 2);
    setFullName(role === 'teacher' ? 'Demo Giáo viên' : 'Demo Học viên');
    navigate('/home');
  };

  return (
    <div className='container grid-12'>
      <Card className='span-12'>
        <PageHeader title='Đăng nhập' subtitle='Đăng nhập bằng email/mật khẩu. Sinh viên tự đăng ký cần MSSV.' breadcrumbs={['Trang chủ']} />
      </Card>

      {DEMO_MODE ? (
        <Card className='span-8 stack-md'>
          <div className='row'>
            <Button onClick={() => runDemo('teacher')}>Demo GV (được cấp sẵn)</Button>
            <Button variant='secondary' onClick={() => runDemo('student')}>Demo SV</Button>
          </div>
        </Card>
      ) : null}

      <Card className='span-8 stack-md'>
        <form className='stack-md' onSubmit={doAuth}>
          <label className='input-wrap'><span className='input-label'>Email</span><input className='input' value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label className='input-wrap'><span className='input-label'>Mật khẩu</span><input type='password' className='input' value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          {isRegister ? (
            <label className='input-wrap'><span className='input-label'>MSSV</span><input className='input' value={studentCode} onChange={(e) => setStudentCode(e.target.value)} required /></label>
          ) : null}
          {error ? <span className='input-helper'>{error}</span> : null}
          <div className='row'>
            <Button type='submit'>{isRegister ? 'Đăng ký SV' : 'Đăng nhập'}</Button>
            <Button type='button' variant='ghost' onClick={() => setIsRegister((v) => !v)}>{isRegister ? 'Đã có tài khoản?' : 'Tạo tài khoản SV'}</Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
