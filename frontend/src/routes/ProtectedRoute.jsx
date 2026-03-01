import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import Card from '../ui/Card';
import Button from '../ui/Button';

export default function ProtectedRoute({ children, allow }) {
  const { role } = useAuth();

  if (!role) return <Navigate to='/' />;

  if (!allow.includes(role)) {
    return (
      <div className='container'>
        <Card className='stack-md'>
          <h2>Bạn chưa có quyền truy cập</h2>
          <p className='page-subtitle'>Vui lòng đăng nhập bằng tài khoản phù hợp để tiếp tục.</p>
          <div><Button onClick={() => window.history.back()}>Quay lại</Button></div>
        </Card>
      </div>
    );
  }

  return children;
}
