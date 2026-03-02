import React from 'react';
import Alert from '../components/Alert';
import { authApi, getErrorMessage } from '../api';
import { useAuth } from '../auth';

export default function LoginPage({ navigate }) {
  const { login } = useAuth();
  const [email, setEmail] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [error, setError] = React.useState('');
  const [loading, setLoading] = React.useState(false);

  const onSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      const response = await authApi.login({ email, password });
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
        <h2>Login</h2>
        <Alert type="error" message={error} />
        <div className="form-group">
          <label htmlFor="email">Email</label>
          <input id="email" value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
        </div>
        <div className="form-group">
          <label htmlFor="password">Password</label>
          <input id="password" value={password} onChange={(e) => setPassword(e.target.value)} type="password" required />
        </div>
        <button disabled={loading} type="submit">{loading ? 'Signing in...' : 'Sign in'}</button>
      </form>
    </div>
  );
}
