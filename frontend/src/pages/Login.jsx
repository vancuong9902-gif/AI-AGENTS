import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import Card from '../ui/Card';
import Button from '../ui/Button';
import PageHeader from '../ui/PageHeader';

export default function Login() {
  const navigate = useNavigate();
  const { role, setRole, userId, setUserId, fullName, setFullName } = useAuth();

  const [localRole, setLocalRole] = useState(role || 'student');
  const [localId, setLocalId] = useState(String(userId ?? 1));
  const [localName, setLocalName] = useState(fullName || '');

  const parsedId = useMemo(() => {
    const n = Number(localId);
    return Number.isFinite(n) && n > 0 ? Math.floor(n) : null;
  }, [localId]);

  const submit = (e) => {
    e?.preventDefault?.();
    if (!parsedId) return;
    setUserId(parsedId);
    setRole(localRole);
    setFullName((localName || '').trim() || null);
    if (localRole === 'teacher') navigate('/teacher/classrooms');
    else navigate('/classrooms');
  };

  return (
    <div className='container grid-12'>
      <Card className='span-12'>
        <PageHeader
          title='Đăng nhập bản demo'
          subtitle='Chọn vai trò và mã người dùng để bắt đầu trải nghiệm hệ thống.'
          breadcrumbs={['Trang chủ']}
        />
      </Card>

      <Card className='span-8 stack-md'>
        <form className='stack-md' onSubmit={submit}>
          <div className='grid-12'>
            <label className='input-wrap span-6' htmlFor='role'>
              <span className='input-label'>Vai trò</span>
              <select id='role' value={localRole} className='input' onChange={(e) => setLocalRole(e.target.value)}>
                <option value='student'>Học viên</option>
                <option value='teacher'>Giáo viên</option>
              </select>
            </label>
            <label className='input-wrap span-6' htmlFor='user-id'>
              <span className='input-label'>Mã người dùng</span>
              <input id='user-id' value={localId} onChange={(e) => setLocalId(e.target.value)} className='input' placeholder='Ví dụ: 1' />
              {!parsedId ? <span className='input-helper'>Mã người dùng phải là số dương.</span> : null}
            </label>
          </div>

          <label className='input-wrap' htmlFor='full-name'>
            <span className='input-label'>Tên hiển thị (tuỳ chọn)</span>
            <input id='full-name' value={localName} onChange={(e) => setLocalName(e.target.value)} className='input' placeholder='Ví dụ: Nguyễn Văn A' />
          </label>

          <div className='row'>
            <Button variant='primary' type='submit' disabled={!parsedId}>Đăng nhập</Button>
            <span className='page-subtitle'>Gợi ý: tài khoản giáo viên demo thường dùng mã 1.</span>
          </div>
        </form>
      </Card>
    </div>
  );
}
