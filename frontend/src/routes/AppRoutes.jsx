import { Navigate, Route, Routes } from 'react-router-dom';
import Login from '../pages/Login';
import Register from '../pages/Register';
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
        path='/teacher/dashboard'
        element={(
          <ProtectedRoute allowedRoles={['teacher']}>
            <RoleDashboard role='teacher' />
          </ProtectedRoute>
        )}
      />

      <Route
        path='/student/dashboard'
        element={(
          <ProtectedRoute allowedRoles={['student']}>
            <RoleDashboard role='student' />
          </ProtectedRoute>
        )}
      />

      <Route path='*' element={<Navigate to='/login' replace />} />
    </Routes>
  );
}
