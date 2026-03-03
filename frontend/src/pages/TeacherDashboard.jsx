import React from 'react';
import Alert from '../components/Alert';
import { useAuth } from '../auth';
import TeacherUpload from '../components/teacher/TeacherUpload';
import TeacherClassSetup from '../components/teacher/TeacherClassSetup';
import TeacherAssessments from '../components/teacher/TeacherAssessments';
import TeacherMonitor from '../components/teacher/TeacherMonitor';
import TeacherReports from '../components/teacher/TeacherReports';

const TABS = [
  { key: 'upload', label: 'B1 · Upload PDF' },
  { key: 'class', label: 'B2 · Tạo lớp học' },
  { key: 'assessments', label: 'B3 · Cấu hình bài kiểm tra' },
  { key: 'monitor', label: 'B4 · Monitor & report' },
  { key: 'reports', label: 'B5 · Xuất báo cáo' },
];

const initialWorkflow = {
  courseId: null,
  uploadReady: false,
  topicsDraft: [],
  selectedTopicIds: [],
  topicsPublished: false,
  classroomId: null,
  inviteCode: '',
  assessmentActivated: false,
  assessmentId: null,
};

export default function TeacherDashboard() {
  const { user } = useAuth();
  const [tab, setTab] = React.useState('upload');
  const [alert, setAlert] = React.useState({ type: 'info', message: '' });
  const [workflow, setWorkflow] = React.useState(initialWorkflow);

  const gotoTab = (nextTab) => {
    if (nextTab) setTab(nextTab);
    setAlert({ type: 'info', message: '' });
  };

  return (
    <div className="shell">
      <div className="page-header">
        <h1>👩‍🏫 Teacher Workflow</h1>
        <p>Xin chào, <strong>{user?.full_name || user?.email}</strong> · Điều phối toàn bộ quy trình dạy học từ upload tài liệu đến xuất báo cáo.</p>
      </div>

      {alert.message && <Alert type={alert.type} message={alert.message} />}

      <div className="tabs">
        {TABS.map((item) => (
          <button key={item.key} className={`tab ${tab === item.key ? 'active' : ''}`} onClick={() => gotoTab(item.key)}>
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'upload' && (
        <TeacherUpload
          setAlert={setAlert}
          workflow={workflow}
          setWorkflow={setWorkflow}
          onContinue={gotoTab}
        />
      )}
      {tab === 'class' && (
        <TeacherClassSetup
          setAlert={setAlert}
          workflow={workflow}
          setWorkflow={setWorkflow}
          onContinue={gotoTab}
        />
      )}
      {tab === 'assessments' && (
        <TeacherAssessments
          setAlert={setAlert}
          workflow={workflow}
          setWorkflow={setWorkflow}
        />
      )}
      {tab === 'monitor' && <TeacherMonitor setAlert={setAlert} workflow={workflow} />}
      {tab === 'reports' && <TeacherReports setAlert={setAlert} workflow={workflow} />}
    </div>
  );
}
