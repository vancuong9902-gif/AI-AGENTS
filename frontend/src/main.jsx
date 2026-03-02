import React from 'react';
import { createRoot } from 'react-dom/client';
import { AuthProvider } from './auth';
import Navbar from './components/Navbar';
import ProtectedRoute from './components/ProtectedRoute';
import LoadingSpinner from './components/LoadingSpinner';
import HomePage from './pages/HomePage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import TeacherDashboard from './pages/TeacherDashboard';
import StudentDashboard from './pages/StudentDashboard';
import TeacherResultsPage from './pages/TeacherResultsPage';
import './styles.css';

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

function RouterView({ path, navigate }) {
  if (path === '/login') return <LoginPage navigate={navigate} />;
  if (path === '/register') return <RegisterPage navigate={navigate} />;
  if (path === '/teacher/results') {
    return (
      <ProtectedRoute role="teacher" navigate={navigate}>
        <TeacherResultsPage>
          <TeacherDashboard />
        </TeacherResultsPage>
      </ProtectedRoute>
    );
  }
  if (path === '/teacher') {
    return (
      <ProtectedRoute role="teacher" navigate={navigate}>
        <TeacherDashboard />
      </ProtectedRoute>
    );
  }
  if (path === '/student') {
    return (
      <ProtectedRoute role="student" navigate={navigate}>
        <StudentDashboard />
      </ProtectedRoute>
    );
  }
  if (path === '/') return <HomePage navigate={navigate} />;
  return <LoadingSpinner label="Redirecting..." />;
}

function App() {
  const { path, navigate } = usePathname();
  React.useEffect(() => {
    if (!['/', '/login', '/register', '/teacher', '/teacher/results', '/student', '/teacher/classrooms'].includes(path)) {
      navigate('/', true);
    }
  }, [path, navigate]);

  return (
    <AuthProvider>
      <Navbar path={path} navigate={navigate} />
      <RouterView path={path} navigate={navigate} />
    </AuthProvider>
  );
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
