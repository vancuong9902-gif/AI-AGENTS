import { FormEvent, useState } from 'react';
import api from '../../utils/api';

export default function RegisterForm() {
  const [form, setForm] = useState({ name: '', email: '', password: '', confirm: '', role: 'STUDENT' });
  const [error, setError] = useState('');

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (form.password !== form.confirm) return setError('Mật khẩu xác nhận không khớp');
    try {
      const { data } = await api.post('/auth/register', { name: form.name, email: form.email, password: form.password, role: form.role });
      localStorage.setItem('token', data.token);
      window.location.href = data.user.role === 'TEACHER' ? '/dashboard/teacher' : '/dashboard/student';
    } catch (err: any) {
      setError(err.response?.data?.error ?? 'Đăng ký thất bại');
    }
  };

  return <form onSubmit={submit} className="space-y-3"><h1>Đăng ký</h1><input placeholder="Họ và tên" value={form.name} onChange={(e)=>setForm({...form,name:e.target.value})} /><input placeholder="Email" value={form.email} onChange={(e)=>setForm({...form,email:e.target.value})} /><input type="password" placeholder="Mật khẩu" value={form.password} onChange={(e)=>setForm({...form,password:e.target.value})} /><input type="password" placeholder="Xác nhận mật khẩu" value={form.confirm} onChange={(e)=>setForm({...form,confirm:e.target.value})} /><select value={form.role} onChange={(e)=>setForm({...form,role:e.target.value})}><option value="TEACHER">Giáo viên</option><option value="STUDENT">Học sinh</option></select>{error && <p>{error}</p>}<button>Tạo tài khoản</button></form>;
}
