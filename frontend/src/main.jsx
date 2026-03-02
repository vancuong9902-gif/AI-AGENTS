import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import './styles.css';

const api = axios.create({ baseURL: '/api', withCredentials: true });

function App() {
  const [user, setUser] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [message, setMessage] = React.useState('');
  const [courseId, setCourseId] = React.useState(null);
  const [topics, setTopics] = React.useState([]);
  const [exam, setExam] = React.useState(null);
  const [timeLeft, setTimeLeft] = React.useState(600);

  const ensurePath = React.useCallback((role) => {
    const target = role === 'teacher' ? '/teacher' : '/student';
    if (window.location.pathname !== target) {
      window.history.replaceState({}, '', target);
    }
  }, []);

  const toStartPage = React.useCallback(() => {
    if (window.location.pathname !== '/') {
      window.history.replaceState({}, '', '/');
    }
  }, []);

  const loadSession = React.useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get('/session/me');
      const currentUser = response?.data?.data;
      if (!currentUser?.role) throw new Error('Session unavailable');
      setUser(currentUser);
      ensurePath(currentUser.role);
    } catch {
      setUser(null);
      toStartPage();
    } finally {
      setLoading(false);
    }
  }, [ensurePath, toStartPage]);

  React.useEffect(() => { loadSession(); }, [loadSession]);

  React.useEffect(() => {
    if (!exam) return;
    const t = setInterval(() => setTimeLeft((v) => Math.max(v - 1, 0)), 1000);
    return () => clearInterval(t);
  }, [exam]);

  React.useEffect(() => {
    if (timeLeft === 0 && exam && user?.role === 'student') submitExam({});
  }, [timeLeft]);

  async function start(role) {
    setLoading(true);
    setMessage('');
    try {
      await api.post('/session/start', { role });
      await loadSession();
    } catch (error) {
      setMessage(error?.response?.data?.detail || error.message || 'Cannot start session');
      setLoading(false);
    }
  }

  async function logout() {
    await api.post('/session/end').catch(() => {});
    setUser(null);
    setExam(null);
    setTopics([]);
    setCourseId(null);
    toStartPage();
  }

  async function uploadPdf(e) {
    const file = e.target.files[0];
    const form = new FormData(); form.append('file', file);
    const r = await api.post('/mvp/courses/upload', form, { headers: { 'Content-Type': 'multipart/form-data' } });
    setCourseId(r.data.data.course_id); setMessage('PDF uploaded.');
  }

  async function genTopics() { const r = await api.post(`/mvp/courses/${courseId}/generate-topics`, {}); setTopics(r.data.data.topics); }
  async function genExam() { const r = await api.post(`/mvp/courses/${courseId}/generate-entry-test`, {}); setExam(r.data.data); setMessage('Entry test generated.'); }
  async function loadStudentCourse() { const r = await api.get('/mvp/student/course'); if (r.data.data.topics) setTopics(r.data.data.topics); else setMessage(r.data.data.message); }
  async function loadStudentExam() { const r = await api.get('/mvp/student/exams/latest'); setExam(r.data.data); setTimeLeft(r.data.data.duration_seconds); }

  async function submitExam(answers) {
    const r = await api.post(`/mvp/student/exams/${exam.exam_id}/submit`, { answers });
    setMessage(`Score: ${r.data.data.score} - ${r.data.data.level}`); setExam(null);
  }

  if (loading) return <div className="shell">Loading...</div>;

  if (!user) {
    return <div className="shell"><h1>AI LMS Demo</h1>{message && <p className="error">{message}</p>}
      <div className="card auth-card stack">
        <p className="muted">Start instantly without login.</p>
        <button onClick={() => start('student')}>Play as Student</button>
        <button className="ghost full" onClick={() => start('teacher')}>Start as Teacher</button>
      </div>
    </div>;
  }

  if (user.role === 'teacher') return <div className="shell"><h2>Teacher Dashboard</h2><button onClick={logout}>End Session</button><input type="file" accept="application/pdf" onChange={uploadPdf} />
    <div className="row"><button onClick={genTopics} disabled={!courseId}>Generate Course</button><button onClick={genExam} disabled={!courseId}>Generate Entry Test</button></div>
    <p>{message}</p>
    {topics.map((t) => <details key={t.title}><summary>{t.title}</summary><p>{t.summary}</p><ul>{t.exercises.map((ex) => <li key={ex}>{ex}</li>)}</ul></details>)}
  </div>;

  return <div className="shell"><h2>Student Dashboard</h2><button onClick={logout}>End Session</button><button onClick={loadStudentCourse}>Load Course</button><button onClick={loadStudentExam}>Take Entry Test</button><p>{message}</p>
    {exam && <div><p>Time left: {timeLeft}s</p>{exam.questions.map((q) => <div key={q.id}><p>{q.question}</p>{q.options.map((op) => <button key={op} onClick={() => submitExam({ [q.id]: op })}>{op}</button>)}</div>)}</div>}
    {topics.map((t) => <details key={t.title}><summary>{t.title}</summary><p>{t.summary}</p><ul>{t.exercises.map((ex) => <li key={ex}>{ex}</li>)}</ul></details>)}
  </div>;
}

createRoot(document.getElementById('app')).render(<App />);
