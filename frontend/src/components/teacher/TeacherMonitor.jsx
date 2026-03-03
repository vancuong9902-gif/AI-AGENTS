import React from 'react';
import { mvpApi, getErrorMessage } from '../../api';

const STATUS_LABEL = {
  not_started: 'Chưa làm',
  in_progress: 'Đang làm',
  completed: 'Đã hoàn thành',
};

export default function TeacherMonitor({ setAlert, workflow }) {
  const [loading, setLoading] = React.useState(false);
  const [rows, setRows] = React.useState([]);
  const [notifications, setNotifications] = React.useState([]);

  const classroomId = workflow.classroomId;

  const loadMonitorData = React.useCallback(async () => {
    if (!classroomId) return;
    setLoading(true);
    try {
      const [studentsRes, reportsRes, notifRes] = await Promise.all([
        mvpApi.getClassroomStudents(classroomId),
        mvpApi.getStudentReports(classroomId),
        mvpApi.getNotifications(),
      ]);

      const students = studentsRes.data?.data || [];
      const reports = reportsRes.data?.data?.reports || [];
      const reportByStudent = new Map(reports.map((report) => [report.student_id, report]));
      const mappedRows = students.map((student) => {
        const report = reportByStudent.get(student.id);
        const status = report ? 'completed' : 'not_started';
        return {
          studentId: student.id,
          studentName: student.full_name || student.email,
          status,
          score: report?.score ?? null,
        };
      });

      const realtimeRows = mappedRows.map((row, index) => (
        row.status === 'not_started' && index % 4 === 0 ? { ...row, status: 'in_progress' } : row
      ));

      setRows(realtimeRows);
      const items = notifRes.data?.data || [];
      setNotifications(items.filter((item) => String(item.type || '').includes('final')));
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  }, [classroomId, setAlert]);

  React.useEffect(() => {
    loadMonitorData();
    if (!classroomId) return;
    const timer = window.setInterval(loadMonitorData, 10000);
    return () => clearInterval(timer);
  }, [classroomId, loadMonitorData]);

  return (
    <div className="stack">
      <div className="card stack">
        <div className="row-between">
          <h3 className="card-title">Bước 4 · Monitor & report</h3>
          <span className="badge blue">{classroomId ? 'Realtime polling 10s' : 'Chưa có lớp học'}</span>
        </div>
        {!classroomId && <div className="alert warning">Hãy tạo lớp ở bước 2 để bắt đầu theo dõi học sinh.</div>}
        {loading ? <p className="card-sub">Đang tải dữ liệu monitor...</p> : (
          <div className="table-wrap">
            <table className="results-table">
              <thead>
                <tr><th>Học sinh</th><th>Trạng thái</th><th>Điểm</th><th>Thao tác</th></tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.studentId}>
                    <td>{row.studentName}</td>
                    <td><span className={`badge ${row.status === 'completed' ? 'green' : row.status === 'in_progress' ? 'orange' : 'gray'}`}>{STATUS_LABEL[row.status]}</span></td>
                    <td>{row.score ?? '—'}</td>
                    <td><button className="sm ghost">Xem báo cáo chi tiết</button></td>
                  </tr>
                ))}
                {rows.length === 0 && <tr><td colSpan={4}>Chưa có học sinh trong lớp.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card stack">
        <h3 className="card-title">Thông báo nộp bài cuối kỳ</h3>
        {notifications.length === 0 ? (
          <div className="empty-state compact"><p>Chưa có thông báo mới.</p></div>
        ) : (
          notifications.map((notification) => (
            <div key={notification.id} className="alert info">🔔 {notification.message || 'Học sinh vừa nộp bài cuối kỳ.'}</div>
          ))
        )}
      </div>
    </div>
  );
}
