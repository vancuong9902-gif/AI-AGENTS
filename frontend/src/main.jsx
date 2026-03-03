import React from 'react';
import { createRoot } from 'react-dom/client';

import App from './App';
import './styles.css';

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
import StudentClassroomSubjects from './pages/StudentClassroomSubjects';
import JoinClassroom from './pages/JoinClassroom';
import ClassroomDetail from './pages/ClassroomDetail';
import ClassroomManagement from './pages/ClassroomManagement';
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
  if (path === '/teacher/classrooms') {
    return (
      <ProtectedRoute role="teacher" navigate={navigate}>
        <ClassroomManagement navigate={navigate} />
      </ProtectedRoute>
    );
  }
  if (path.startsWith('/teacher/classrooms/')) {
    const classroomId = Number(path.split('/')[3]);
    return (
      <ProtectedRoute role="teacher" navigate={navigate}>
        <ClassroomDetail classroomId={classroomId} />
      </ProtectedRoute>
    );
  }
  if (path === '/student/join-classroom') {
    return (
      <ProtectedRoute role="student" navigate={navigate}>
        <JoinClassroom navigate={navigate} />
      </ProtectedRoute>
    );
  }
  if (path.startsWith('/student/classrooms/') && path.endsWith('/subjects')) {
    const classroomId = Number(path.split('/')[3]);
    return (
      <ProtectedRoute role="student" navigate={navigate}>
        <StudentClassroomSubjects classroomId={classroomId} />
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
    if (!(path === '/' || path === '/login' || path === '/register' || path === '/teacher' || path === '/teacher/results' || path === '/student' || path === '/teacher/classrooms' || path === '/student/join-classroom' || path.startsWith('/teacher/classrooms/') || (path.startsWith('/student/classrooms/') && path.endsWith('/subjects')))) {
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

const container = document.getElementById('root');

if (!container) {
  throw new Error('Root element #root not found in index.html');
}

createRoot(container).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
