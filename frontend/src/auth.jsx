import React from 'react';
import { authApi } from './api';

const AuthContext = React.createContext({
  user: null,
  isLoading: true,
  login: async () => {},
  logout: () => {},
  isLoggedIn: false,
});

export function useAuth() {
  return React.useContext(AuthContext);
}

export function AuthProvider({ children }) {
  const [user, setUser] = React.useState(null);
  const [isLoading, setIsLoading] = React.useState(true);

  const logout = React.useCallback(() => {
    localStorage.removeItem('token');
    localStorage.removeItem('userId');
    localStorage.removeItem('userRole');
    localStorage.removeItem('userEmail');
    localStorage.removeItem('userName');
    setUser(null);
  }, []);

  const login = React.useCallback(async (token, userData) => {
    if (token) {
      localStorage.setItem('token', token);
    } else {
      localStorage.removeItem('token');
    }
    localStorage.setItem('userId', String(userData.id));
    localStorage.setItem('userRole', userData.role || 'student');
    if (userData.email) localStorage.setItem('userEmail', userData.email);
    if (userData.full_name) localStorage.setItem('userName', userData.full_name);
    setUser(userData);
  }, []);

  React.useEffect(() => {
    let mounted = true;
    const bootstrap = async () => {
      const token = localStorage.getItem('token');
      const userId = localStorage.getItem('userId');
      const role = localStorage.getItem('userRole');
      if (!token && !userId) {
        setIsLoading(false);
        return;
      }

      try {
        const response = await authApi.me();
        if (!mounted) return;
        setUser(response.data.data);
      } catch {
        if (!mounted) return;
        if (userId && role) {
          setUser({
            id: Number(userId),
            role,
            email: localStorage.getItem('userEmail') || '',
            full_name: localStorage.getItem('userName') || '',
          });
        } else {
          logout();
        }
      } finally {
        if (mounted) setIsLoading(false);
      }
    };

    bootstrap();
    const onForcedLogout = () => logout();
    window.addEventListener('auth:logout', onForcedLogout);
    return () => {
      mounted = false;
      window.removeEventListener('auth:logout', onForcedLogout);
    };
  }, [logout]);

  const value = React.useMemo(
    () => ({ user, isLoading, login, logout, isLoggedIn: Boolean(user) }),
    [user, isLoading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
