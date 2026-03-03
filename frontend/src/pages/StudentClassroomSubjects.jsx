import React from 'react';
import { mvpApi, getErrorMessage } from '../api';
import Alert from '../components/Alert';
import LoadingSpinner from '../components/LoadingSpinner';

export default function StudentClassroomSubjects({ classroomId }) {
  const [subjects, setSubjects] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [alert, setAlert] = React.useState(null);

  React.useEffect(() => {
    const run = async () => {
      setLoading(true);
      try {
        const res = await mvpApi.getStudentClassroomSubjects(classroomId);
        setSubjects(res.data?.data || []);
      } catch (err) {
        setAlert({ type: 'error', message: getErrorMessage(err) });
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [classroomId]);

  return (
    <div className="page-container stack">
      {alert && <Alert type={alert.type} message={alert.message} onClose={() => setAlert(null)} />}
      <h2>Môn học trong lớp</h2>
      {loading ? <LoadingSpinner label="Đang tải môn học..." /> : subjects.length === 0 ? <div className="empty-state"><p>Chưa có môn học.</p></div> : (
        <div className="grid-3">
          {subjects.map((s) => <div className="card" key={s.id}><div className="card-title">{s.title}</div><p>{s.summary}</p></div>)}
        </div>
      )}
    </div>
  );
}
