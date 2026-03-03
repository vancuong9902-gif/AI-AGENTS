import React from 'react';
import { mvpApi, getErrorMessage } from '../api';
import Alert from '../components/Alert';

export default function JoinClassroom({ navigate }) {
  const [inviteCode, setInviteCode] = React.useState('');
  const [alert, setAlert] = React.useState(null);
  const [loading, setLoading] = React.useState(false);

  const onJoin = async () => {
    if (inviteCode.trim().length !== 8) return;
    setLoading(true);
    try {
      const res = await mvpApi.joinClassroom(inviteCode.trim().toUpperCase());
      const cls = res.data?.data;
      navigate(`/student/classrooms/${cls.id}/subjects`);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-container stack">
      {alert && <Alert type={alert.type} message={alert.message} onClose={() => setAlert(null)} />}
      <h2>Tham gia lớp học</h2>
      <input value={inviteCode} onChange={(e) => setInviteCode(e.target.value.toUpperCase())} maxLength={8} placeholder="Mã mời 8 ký tự" />
      <button onClick={onJoin} disabled={inviteCode.trim().length !== 8 || loading}>{loading ? 'Đang tham gia...' : 'Tham gia'}</button>
    </div>
  );
}
