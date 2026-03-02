import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import './styles.css';

const api = axios.create({ baseURL: '/api', withCredentials: true });

function HomePage() {
  const goTo = (path) => window.history.pushState({}, '', path);

  return (
    <div className="shell">
      <h1>AI LMS Demo</h1>
      <div className="card auth-card stack">
        <p className="muted">Demo mode: no login required.</p>
        <button onClick={() => { goTo('/student'); window.dispatchEvent(new PopStateEvent('popstate')); }}>
          Go to Student
        </button>
        <button className="ghost full" onClick={() => { goTo('/teacher'); window.dispatchEvent(new PopStateEvent('popstate')); }}>
          Go to Teacher
        </button>
      </div>
    </div>
  );
}

function App() {
  const [path, setPath] = React.useState(window.location.pathname);
  const [message, setMessage] = React.useState('');
  const [courseId, setCourseId] = React.useState(null);
  const [topics, setTopics] = React.useState([]);
  const [exam, setExam] = React.useState(null);
  const [timeLeft, setTimeLeft] = React.useState(600);

  React.useEffect(() => {
    const onPopState = () => setPath(window.location.pathname);
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  React.useEffect(() => {
    if (!exam) return;
    const t = setInterval(() => setTimeLeft((v) => Math.max(v - 1, 0)), 1000);
    return () => clearInterval(t);
  }, [exam]);

  React.useEffect(() => {
    if (timeLeft === 0 && exam && path === '/student') submitExam({});
  }, [timeLeft]);

  const roleHeaders = React.useMemo(() => {
    if (path === '/teacher') return { 'X-User-Id': '1', 'X-User-Role': 'teacher' };
    return { 'X-User-Id': '2', 'X-User-Role': 'student' };
  }, [path]);

  function navTo(nextPath) {
    window.history.pushState({}, '', nextPath);
    setPath(nextPath);
    setMessage('');
  }

  async function uploadPdf(e) {
    const file = e.target.files[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    const r = await api.post('/mvp/courses/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data', ...roleHeaders },
    });
    setCourseId(r.data.data.course_id);
    setMessage('PDF uploaded.');
  }

  async function genTopics() {
    const r = await api.post(`/mvp/courses/${courseId}/generate-topics`, {}, { headers: roleHeaders });
    setTopics(r.data.data.topics);
  }

  async function genExam() {
    const r = await api.post(`/mvp/courses/${courseId}/generate-entry-test`, {}, { headers: roleHeaders });
    setExam(r.data.data);
    setMessage('Entry test generated.');
  }

  async function loadStudentCourse() {
    const r = await api.get('/mvp/student/course', { headers: roleHeaders });
    if (r.data.data.topics) setTopics(r.data.data.topics);
    else setMessage(r.data.data.message);
  }

  async function loadStudentExam() {
    const r = await api.get('/mvp/student/exams/latest', { headers: roleHeaders });
    setExam(r.data.data);
    setTimeLeft(r.data.data.duration_seconds);
  }

  async function submitExam(answers) {
    const r = await api.post(`/mvp/student/exams/${exam.exam_id}/submit`, { answers }, { headers: roleHeaders });
    setMessage(`Score: ${r.data.data.score} - ${r.data.data.level}`);
    setExam(null);
  }

  if (path === '/teacher') {
    return <div className="shell"><h2>Teacher Dashboard</h2><button onClick={() => navTo('/')}>Back to Home</button><input type="file" accept="application/pdf" onChange={uploadPdf} />
      <div className="row"><button onClick={genTopics} disabled={!courseId}>Generate Course</button><button onClick={genExam} disabled={!courseId}>Generate Entry Test</button></div>
      <p>{message}</p>
      {topics.map((t) => <details key={t.title}><summary>{t.title}</summary><p>{t.summary}</p><ul>{t.exercises.map((ex) => <li key={ex}>{ex}</li>)}</ul></details>)}
    </div>;
  }

  if (path === '/student') {
    return <div className="shell"><h2>Student Dashboard</h2><button onClick={() => navTo('/')}>Back to Home</button><button onClick={loadStudentCourse}>Load Course</button><button onClick={loadStudentExam}>Take Entry Test</button><p>{message}</p>
      {exam && <div><p>Time left: {timeLeft}s</p>{exam.questions.map((q) => <div key={q.id}><p>{q.question}</p>{q.options.map((op) => <button key={op} onClick={() => submitExam({ [q.id]: op })}>{op}</button>)}</div>)}</div>}
      {topics.map((t) => <details key={t.title}><summary>{t.title}</summary><p>{t.summary}</p><ul>{t.exercises.map((ex) => <li key={ex}>{ex}</li>)}</ul></details>)}
    </div>;
  }

  return <HomePage />;
}

createRoot(document.getElementById('app')).render(<App />);
