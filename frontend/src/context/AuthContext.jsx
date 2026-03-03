import React from 'react';

const AUTH_ENABLED = String(import.meta.env.VITE_AUTH_ENABLED ?? 'true').toLowerCase() !== 'false';

const AuthContext = React.createContext({
  user: null,
  login: () => {},
  logout: () => {},
  isAuthenticated: false,
  isTeacher: false,
  isStudent: false,
  authEnabled: AUTH_ENABLED,
});

export function useAuth() {
  return React.useContext(AuthContext);
}

export function AuthProvider({ children }) {
  const [user, setUser] = React.useState(null);

  React.useEffect(() => {
    const storedUser = localStorage.getItem('user');
    if (!storedUser) return;
    try {
      setUser(JSON.parse(storedUser));
    } catch {
      localStorage.removeItem('user');
    }
  }, []);

  const login = React.useCallback((token, userData) => {
    if (token) {
      localStorage.setItem('access_token', token);
    }
    localStorage.setItem('user', JSON.stringify(userData));
    setUser(userData);
  }, []);

  const logout = React.useCallback(() => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    setUser(null);
  }, []);

  const value = React.useMemo(() => {
    const role = user?.role;
    return {
      user,
      login,
      logout,
      isAuthenticated: Boolean(user),
      isLoggedIn: Boolean(user),
      isTeacher: role === 'teacher',
      isStudent: role === 'student',
      authEnabled: AUTH_ENABLED,
    };
  }, [login, logout, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
