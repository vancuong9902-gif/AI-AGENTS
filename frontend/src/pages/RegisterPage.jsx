import React from 'react';
import Alert from '../components/Alert';
import { authApi, getErrorMessage } from '../api';
import { useAuth } from '../auth';

export default function RegisterPage({ navigate }) {
  const { login } = useAuth();
  const [form, setForm] = React.useState({ name: '', email: '', password: '', role: 'student' });
  const [error, setError] = React.useState('');
  const [loading, setLoading] = React.useState(false);

  const update = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const onSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      const response = await authApi.register(form);
      const data = response.data.data;
      await login(data.token?.access_token, data.user);
      navigate(data.user.role === 'teacher' ? '/teacher' : '/student');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="shell auth-form">
      <form className="card" onSubmit={onSubmit}>
        <h2>Register</h2>
        <Alert type="error" message={error} />
        <div className="form-group"><label>Name</label><input required value={form.name} onChange={(e) => update('name', e.target.value)} /></div>
        <div className="form-group"><label>Email</label><input type="email" required value={form.email} onChange={(e) => update('email', e.target.value)} /></div>
        <div className="form-group"><label>Password</label><input type="password" required value={form.password} onChange={(e) => update('password', e.target.value)} /></div>
        <div className="form-group">
          <label>Role</label>
          <select value={form.role} onChange={(e) => update('role', e.target.value)}>
            <option value="student">Student</option>
            <option value="teacher">Teacher</option>
          </select>
        </div>
        <button disabled={loading}>{loading ? 'Creating...' : 'Create account'}</button>
      </form>
    </div>
  );
}
