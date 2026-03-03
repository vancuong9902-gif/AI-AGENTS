import React from 'react';
import { mvpApi, getErrorMessage } from '../../api';

export default function TeacherClassSetup({ setAlert, workflow, setWorkflow, onContinue }) {
  const [className, setClassName] = React.useState('');
  const [creating, setCreating] = React.useState(false);

  const createClassroom = async () => {
    if (!className.trim()) return;
    setCreating(true);
    try {
      const res = await mvpApi.createClassroomV2(className.trim());
      const classroom = res.data?.data || res.data;
      setWorkflow((prev) => ({ ...prev, classroomId: classroom?.id, inviteCode: classroom?.join_code }));
      setAlert({ type: 'success', message: '✅ Đã tạo lớp học thành công.' });
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setCreating(false);
    }
  };

  const copyInvite = async () => {
    if (!workflow.inviteCode) return;
    await navigator.clipboard.writeText(workflow.inviteCode);
    setAlert({ type: 'success', message: '✅ Đã copy invite code.' });
  };

  return (
    <div className="card stack">
      <h3 className="card-title">Bước 2 · Tạo lớp học</h3>
      {!workflow.topicsPublished && (
        <div className="alert warning">Sau khi publish topics, hệ thống sẽ gợi ý tạo lớp học mới để mời học sinh.</div>
      )}

      <div className="row">
        <input value={className} onChange={(e) => setClassName(e.target.value)} placeholder="VD: Lớp Toán 10A" />
        <button onClick={createClassroom} disabled={creating || !className.trim() || !workflow.topicsPublished}>Tạo lớp</button>
      </div>

      {workflow.inviteCode && (
        <div className="alert success row-between">
          <span>Invite code: <strong>{workflow.inviteCode}</strong></span>
          <button className="sm ghost" onClick={copyInvite}>Copy/share</button>
        </div>
      )}

      <div className="row">
        <button className="success-btn" onClick={() => onContinue?.('assessments')} disabled={!workflow.classroomId}>Tiếp tục cấu hình bài kiểm tra</button>
      </div>
    </div>
  );
}
