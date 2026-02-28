import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Navbar() {
  const { role, userId, logout } = useAuth();
  const nav = useNavigate();
  const student = [
    ['/classrooms','Lớp học'], ['/assessments','Bài tổng hợp'], ['/learning-path','Learning Path'], ['/tutor','Tutor AI'], ['/analytics','Analytics'],
  ];
  const teacher = [
    ['/upload','Upload'], ['/teacher/files','Thư viện tài liệu'], ['/teacher/classrooms','Lớp học'], ['/teacher/assessments','Quản lý bài'], ['/teacher/progress','Progress'], ['/teacher/analytics','Analytics'], ['/teacher/infra','Infra'],
  ];
  const items = role === 'teacher' ? teacher : role === 'student' ? student : [];

  return (
    <>
      <div className='brand'>🎓 AI-Agents LMS</div>
      <div className='nav-section'>
        <NavLink className={({isActive})=>`nav-item ${isActive ? 'active' : ''}`} to='/'>Đăng nhập</NavLink>
        {items.map(([to,label]) => <NavLink key={to} className={({isActive})=>`nav-item ${isActive ? 'active' : ''}`} to={to}>{label}</NavLink>)}
        <NavLink className={({isActive})=>`nav-item ${isActive ? 'active' : ''}`} to='/health'>Health</NavLink>
      </div>
      <div style={{marginTop:16,fontSize:13,color:'var(--muted)'}}>Role: <b>{role || 'guest'}</b> · User ID: <b>{userId ?? 1}</b></div>
      <button className='logout-btn' style={{marginTop:10}} onClick={()=>{ logout(); nav('/'); }}>Logout</button>
    </>
  );
}
