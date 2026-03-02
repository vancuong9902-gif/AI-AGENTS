import { useMemo, useState } from 'react';
import { AuthContext } from './authContextBase';

function parseStoredUser() {
  const stored = localStorage.getItem('user');
  if (!stored) {
    return null;
  }

  try {
    return JSON.parse(stored);
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('token'));
  const [user, setUser] = useState(parseStoredUser);

  const login = ({ token: nextToken, user: nextUser }) => {
    setToken(nextToken);
    setUser(nextUser);
    localStorage.setItem('token', nextToken);
    localStorage.setItem('role', nextUser?.role || 'student');
    localStorage.setItem('user', JSON.stringify(nextUser || null));
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem('token');
    localStorage.removeItem('role');
    localStorage.removeItem('user');
  };

  const value = useMemo(
    () => ({
      user,
      token,
      role: user?.role || localStorage.getItem('role') || null,
      login,
      logout,
    }),
    [token, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
