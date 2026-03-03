import React from 'react';
import Alert from '../components/Alert';
import { useAuth } from '../auth';

export default function StudentDashboard() {
  const { user } = useAuth();
  const [alert, setAlert] = React.useState({ type: 'info', message: '' });

  React.useEffect(() => {
    setAlert({ type: 'info', message: '' });
  }, [user?.id]);

  return (
    <div className="shell stack">
      <div className="page-header">
        <h1>👨‍🎓 Student Dashboard</h1>
        <p>Xin chào <strong>{user?.full_name || user?.email || 'học sinh'}</strong></p>
      </div>

      {alert.message && <Alert type={alert.type} message={alert.message} />}

      <div className="card">
        <h3>Đang cập nhật</h3>
        <p>Tính năng dashboard đang được chuẩn hóa lại.</p>
      </div>
    </div>
  );
}
