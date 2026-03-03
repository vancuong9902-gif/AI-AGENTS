import React from 'react';
import { downloadBlob, mvpApi, getErrorMessage } from '../../api';

const REPORT_TABS = [
  { key: 'class', label: 'Báo cáo lớp' },
  { key: 'student', label: 'Báo cáo từng học sinh' },
  { key: 'exam', label: 'Xuất đề thi' },
];

export default function TeacherReports({ setAlert, workflow }) {
  const [tab, setTab] = React.useState('class');
  const [loading, setLoading] = React.useState(false);

  const classroomId = workflow.classroomId;

  const exportClass = async (format) => {
    if (!classroomId) return;
    setLoading(true);
    try {
      const res = await mvpApi.exportClassReportPDF(classroomId);
      const filename = format === 'pdf' ? 'bao-cao-lop.pdf' : 'bao-cao-lop.docx';
      downloadBlob(res.data, filename);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  const exportExcel = async () => {
    if (!classroomId) return;
    setLoading(true);
    try {
      const latest = await mvpApi.getClassroomDashboard(classroomId);
      const reportId = latest.data?.data?.latest_report_id;
      if (!reportId) {
        setAlert({ type: 'error', message: '⚠️ Chưa có report để xuất Excel.' });
      } else {
        const res = await mvpApi.exportClassReportExcel(classroomId, reportId);
        downloadBlob(res.data, 'bang-diem.xlsx');
      }
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  const exportExamWord = async () => {
    setLoading(true);
    try {
      const res = await mvpApi.generateExamDocx(workflow.courseId || null, 1, 20, 'multiple_choice');
      if (res.data instanceof Blob) {
        downloadBlob(res.data, 'de-thi.docx');
      }
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card stack">
      <div className="row-between">
        <h3 className="card-title">Bước 5 · Xuất báo cáo</h3>
        <span className="badge gray">{classroomId ? `Lớp #${classroomId}` : 'Chưa chọn lớp'}</span>
      </div>

      <div className="tabs nested-tabs">
        {REPORT_TABS.map((item) => (
          <button key={item.key} className={`tab ${tab === item.key ? 'active' : ''}`} onClick={() => setTab(item.key)}>
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'class' && (
        <div className="row">
          <button onClick={() => exportClass('pdf')} disabled={loading || !classroomId}>Export PDF báo cáo lớp</button>
        </div>
      )}
      {tab === 'student' && (
        <div className="row">
          <button onClick={exportExcel} disabled={loading || !classroomId}>Export Excel bảng điểm</button>
        </div>
      )}
      {tab === 'exam' && (
        <div className="row">
          <button onClick={exportExamWord} disabled={loading}>Sinh đề thi Word</button>
        </div>
      )}
    </div>
  );
}
