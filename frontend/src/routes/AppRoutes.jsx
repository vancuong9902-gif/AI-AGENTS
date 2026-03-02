import { Navigate, Route, Routes } from 'react-router-dom';
import Login from '../pages/Login';
import Register from '../pages/Register';
import StudentDashboard from '../pages/StudentDashboard';
import TeacherDashboard from '../pages/TeacherDashboard';
import RoleDashboard from '../pages/RoleDashboard';
import ProtectedRoute from './ProtectedRoute';

export default function AppRoutes() {
  return (
    <Routes>
      <Route path='/' element={<Navigate to='/login' replace />} />
      <Route path='/login' element={<Login />} />
      <Route path='/register' element={<Register />} />


      <Route
        path='/admin/dashboard'
        element={(
          <ProtectedRoute allowedRoles={['admin']}>
            <RoleDashboard role='admin' />
          </ProtectedRoute>
        )}
      />

      <Route
        path='/student'
        element={(
          <ProtectedRoute allowedRoles={['student']}>
            <StudentDashboard />
          </ProtectedRoute>
        )}
      />
      <Route
        path='/teacher'
        element={(
          <ProtectedRoute allowedRoles={['teacher']}>
            <TeacherDashboard />
          </ProtectedRoute>
        )}
      />

      <Route path='/student/dashboard' element={<Navigate to='/student' replace />} />
      <Route path='/teacher/dashboard' element={<Navigate to='/teacher' replace />} />

      <Route path='*' element={<Navigate to='/login' replace />} />
    </Routes>
  );
}
