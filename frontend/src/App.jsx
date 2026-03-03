import React from 'react';
import Navbar from './components/Navbar';
import ProtectedRoute from './components/ProtectedRoute';
import { AuthProvider, useAuth } from './context/AuthContext';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import TeacherDashboard from './pages/TeacherDashboard';
import StudentDashboard from './pages/StudentDashboard';

function usePathname() {
  const [path, setPath] = React.useState(window.location.pathname);

  React.useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const navigate = React.useCallback((nextPath, replace = false) => {
    if (replace) {
      window.history.replaceState({}, '', nextPath);
    } else {
      window.history.pushState({}, '', nextPath);
    }
    setPath(nextPath);
  }, []);

  return { path, navigate };
}

function TeacherLayout() {
  return <TeacherDashboard />;
}

function StudentLayout() {
  return <StudentDashboard />;
}

function HomeRedirect({ navigate }) {
  const { isAuthenticated, isTeacher, isStudent } = useAuth();

  React.useEffect(() => {
    if (!isAuthenticated) {
      navigate('/login', true);
      return;
    }

    if (isTeacher) {
      navigate('/teacher/dashboard', true);
      return;
    }

    if (isStudent) {
      navigate('/student/dashboard', true);
      return;
    }

    navigate('/login', true);
  }, [isAuthenticated, isStudent, isTeacher, navigate]);

  return null;
}

function RouterView({ path, navigate }) {
  if (path === '/login') return <LoginPage navigate={navigate} />;
  if (path === '/register') return <RegisterPage navigate={navigate} />;

  if (path.startsWith('/teacher/')) {
    return (
      <ProtectedRoute role="teacher" navigate={navigate}>
        <TeacherLayout />
      </ProtectedRoute>
    );
  }

  if (path.startsWith('/student/')) {
    return (
      <ProtectedRoute role="student" navigate={navigate}>
        <StudentLayout />
      </ProtectedRoute>
    );
  }

  if (path === '/') {
    return <HomeRedirect navigate={navigate} />;
  }

  navigate('/', true);
  return null;
}

export default function App() {
  const { path, navigate } = usePathname();

  return (
    <AuthProvider>
      <Navbar path={path} navigate={navigate} />
      <RouterView path={path} navigate={navigate} />
    </AuthProvider>
  );
}
