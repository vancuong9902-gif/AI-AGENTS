import React from 'react';
import { mvpApi, getErrorMessage } from '../api';
import Alert from '../components/Alert';
import LoadingSpinner from '../components/LoadingSpinner';

export default function ClassroomManagement({ navigate }) {
  const [classes, setClasses] = React.useState([]);
  const [courses, setCourses] = React.useState([]);
  const [name, setName] = React.useState('');
  const [courseId, setCourseId] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [showModal, setShowModal] = React.useState(false);
  const [alert, setAlert] = React.useState(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const [clsRes, courseRes] = await Promise.all([mvpApi.listTeacherClassrooms(), mvpApi.getMyCourses()]);
      setClasses(clsRes.data?.data?.items || []);
      setCourses(courseRes.data?.data || []);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => { load(); }, [load]);

  const onCreate = async () => {
    if (!name.trim()) return;
    setLoading(true);
    try {
      await mvpApi.createTeacherClassroom({ name: name.trim(), course_id: courseId ? Number(courseId) : null });
      setName('');
      setCourseId('');
      setShowModal(false);
      await load();
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-container stack">
      {alert && <Alert type={alert.type} message={alert.message} onClose={() => setAlert(null)} />}
      <div className="row-between">
        <h2>Quản lý lớp học</h2>
        <button onClick={() => setShowModal(true)}>Tạo lớp mới</button>
      </div>
      {loading ? <LoadingSpinner label="Đang tải lớp học..." /> : (
        <div className="grid-3">
          {classes.map((c) => (
            <div key={c.id} className="card stack">
              <div className="card-title">{c.name}</div>
              <div>Môn học: {c.course_id || 'Chưa chọn'}</div>
              <div>Số học sinh: {c.student_count || 0}</div>
              <div className="row-between">
                <span className="badge blue">{c.invite_code}</span>
                <button className="ghost sm" onClick={() => navigator.clipboard.writeText(c.invite_code || '')}>Copy</button>
              </div>
              <button className="sm" onClick={() => navigate(`/teacher/classrooms/${c.id}`)}>Xem chi tiết</button>
            </div>
          ))}
        </div>
      )}

      {showModal && (
        <div className="modal-backdrop">
          <div className="modal-card stack">
            <h3>Tạo lớp mới</h3>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Tên lớp" />
            <select value={courseId} onChange={(e) => setCourseId(e.target.value)}>
              <option value="">-- Chọn môn học --</option>
              {courses.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
            </select>
            <div className="row">
              <button className="ghost" onClick={() => setShowModal(false)}>Hủy</button>
              <button onClick={onCreate}>Tạo lớp</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
