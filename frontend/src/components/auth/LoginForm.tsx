import { FormEvent, useState } from 'react';
import api from '../../utils/api';

export default function LoginForm() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const { data } = await api.post('/auth/login', { email, password });
      localStorage.setItem('token', data.token);
      window.location.href = data.user.role === 'TEACHER' ? '/dashboard/teacher' : '/dashboard/student';
    } catch (err: any) {
      setError(err.response?.data?.error ?? 'Đăng nhập thất bại');
    }
  };

  return <form onSubmit={submit} className="space-y-3"><h1>Đăng nhập</h1><input placeholder="Email" value={email} onChange={(e)=>setEmail(e.target.value)} /><input placeholder="Mật khẩu" type="password" value={password} onChange={(e)=>setPassword(e.target.value)} />{error && <p>{error}</p>}<button>Đăng nhập</button></form>;
}
