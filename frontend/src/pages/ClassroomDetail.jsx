import React from 'react';
import { mvpApi, downloadBlob, getErrorMessage } from '../api';
import Alert from '../components/Alert';
import LoadingSpinner from '../components/LoadingSpinner';

export default function ClassroomDetail({ classroomId }) {
  const [tab, setTab] = React.useState('students');
  const [detail, setDetail] = React.useState(null);
  const [students, setStudents] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [alert, setAlert] = React.useState(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const [dRes, sRes] = await Promise.all([
        mvpApi.getTeacherClassroomDetail(classroomId),
        mvpApi.getTeacherClassroomStudents(classroomId),
      ]);
      setDetail(dRes.data?.data);
      setStudents(sRes.data?.data?.items || []);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  }, [classroomId]);

  React.useEffect(() => { load(); }, [load]);

  const exportExcel = async () => {
    try {
      const report = await mvpApi.getClassroomDashboard(classroomId);
      const reportId = report.data?.data?.report_id;
      if (!reportId) return;
      const res = await mvpApi.exportClassReportExcel(classroomId, reportId);
      downloadBlob(res.data, `classroom-${classroomId}.xlsx`);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    }
  };

  return (
    <div className="page-container stack">
      {alert && <Alert type={alert.type} message={alert.message} onClose={() => setAlert(null)} />}
      {loading ? <LoadingSpinner label="Đang tải chi tiết lớp..." /> : (
        <>
          <div className="card stack">
            <h2>{detail?.name}</h2>
            <div className="invite-code-box">Mã mời: {detail?.invite_code}</div>
            <button className="sm" onClick={exportExcel}>Xuất Excel danh sách lớp</button>
          </div>

          <div className="row">
            <button className={tab === 'students' ? '' : 'ghost'} onClick={() => setTab('students')}>Học sinh</button>
            <button className={tab === 'stats' ? '' : 'ghost'} onClick={() => setTab('stats')}>Thống kê</button>
            <button className={tab === 'reports' ? '' : 'ghost'} onClick={() => setTab('reports')}>Báo cáo</button>
          </div>

          {tab === 'students' && (
            <div className="card">
              <table className="table">
                <thead><tr><th>Tên</th><th>Email</th><th>Điểm đầu vào</th><th>Level</th><th>Điểm cuối kỳ</th></tr></thead>
                <tbody>
                  {students.map((s) => (
                    <tr key={s.id}><td>{s.full_name || '-'}</td><td>{s.email}</td><td>{s.placement_score ?? '-'}</td><td>{s.level || '-'}</td><td>{s.final_score ?? '-'}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {tab === 'stats' && <div className="card">Thống kê lớp đang được cập nhật.</div>}
          {tab === 'reports' && <div className="card">Báo cáo lớp đang được cập nhật.</div>}
        </>
      )}
    </div>
  );
}
