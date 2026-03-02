import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import './styles.css';

const api = axios.create({ baseURL: '/api' });

function App() {
  const [token, setToken] = React.useState(localStorage.getItem('token') || '');
  const [user, setUser] = React.useState(null);
  const [mode, setMode] = React.useState('login');
  const [message, setMessage] = React.useState('');
  const [courseId, setCourseId] = React.useState(null);
  const [topics, setTopics] = React.useState([]);
  const [exam, setExam] = React.useState(null);
  const [timeLeft, setTimeLeft] = React.useState(600);

  React.useEffect(() => {
    if (!token) return;
    api.get('/auth/me', { headers: { Authorization: `Bearer ${token}` } }).then((r) => setUser(r.data.data)).catch(() => logout());
  }, [token]);

  React.useEffect(() => {
    if (!exam) return;
    const t = setInterval(() => setTimeLeft((v) => Math.max(v - 1, 0)), 1000);
    return () => clearInterval(t);
  }, [exam]);

  React.useEffect(() => {
    if (timeLeft === 0 && exam && user?.role === 'student') submitExam({});
  }, [timeLeft]);

  const logout = () => { localStorage.removeItem('token'); setToken(''); setUser(null); setExam(null); setTopics([]); };

  const authHeaders = { Authorization: `Bearer ${token}` };

  async function login(e) {
    e.preventDefault();
    const form = new FormData(e.target);
    const r = await api.post('/login', { email: form.get('email'), password: form.get('password') });
    localStorage.setItem('token', r.data.data.access_token);
    setToken(r.data.data.access_token);
    setMessage('');
  }

  async function register(e) {
    e.preventDefault();
    const form = new FormData(e.target);
    const payload = { email: form.get('email'), password: form.get('password'), role: form.get('role'), full_name: form.get('full_name') };
    if (payload.role === 'student') payload.student_code = `S-${Date.now()}`;
    await api.post('/auth/register', payload);
    setMode('login');
    setMessage('Registration successful. Please login.');
  }

  async function uploadPdf(e) {
    const file = e.target.files[0];
    const form = new FormData(); form.append('file', file);
    const r = await api.post('/mvp/courses/upload', form, { headers: { ...authHeaders, 'Content-Type': 'multipart/form-data' } });
    setCourseId(r.data.data.course_id); setMessage('PDF uploaded.');
  }

  async function genTopics() { const r = await api.post(`/mvp/courses/${courseId}/generate-topics`, {}, { headers: authHeaders }); setTopics(r.data.data.topics); }
  async function genExam() { const r = await api.post(`/mvp/courses/${courseId}/generate-entry-test`, {}, { headers: authHeaders }); setExam(r.data.data); setMessage('Entry test generated.'); }
  async function loadStudentCourse() { const r = await api.get('/mvp/student/course', { headers: authHeaders }); if (r.data.data.topics) setTopics(r.data.data.topics); else setMessage(r.data.data.message); }
  async function loadStudentExam() { const r = await api.get('/mvp/student/exams/latest', { headers: authHeaders }); setExam(r.data.data); setTimeLeft(r.data.data.duration_seconds); }

  async function submitExam(answers) {
    const r = await api.post(`/mvp/student/exams/${exam.exam_id}/submit`, { answers }, { headers: authHeaders });
    setMessage(`Score: ${r.data.data.score} - ${r.data.data.level}`); setExam(null);
  }

  if (!token) return <div className="shell"><h1>AI LMS Demo</h1>{message && <p>{message}</p>}
    {mode === 'login' ? <form onSubmit={login} className="stack"><input name="email" placeholder="email" /><input name="password" type="password" placeholder="password" /><button>Login</button><button type="button" onClick={() => setMode('register')}>Go register</button></form>
      : <form onSubmit={register} className="stack"><input name="full_name" placeholder="Full name" /><input name="email" placeholder="email" /><input name="password" type="password" placeholder="password" /><select name="role"><option value="teacher">teacher</option><option value="student">student</option></select><button>Register</button><button type="button" onClick={() => setMode('login')}>Back</button></form>}
  </div>;

  if (!user) return <div className="shell">Loading...</div>;

  if (user.role === 'teacher') return <div className="shell"><h2>Teacher Dashboard</h2><button onClick={logout}>Logout</button><input type="file" accept="application/pdf" onChange={uploadPdf} />
    <div className="row"><button onClick={genTopics} disabled={!courseId}>Generate Course</button><button onClick={genExam} disabled={!courseId}>Generate Entry Test</button></div>
    <p>{message}</p>
    {topics.map((t) => <details key={t.title}><summary>{t.title}</summary><p>{t.summary}</p><ul>{t.exercises.map((ex) => <li key={ex}>{ex}</li>)}</ul></details>)}
  </div>;

  return <div className="shell"><h2>Student Dashboard</h2><button onClick={logout}>Logout</button><button onClick={loadStudentCourse}>Load Course</button><button onClick={loadStudentExam}>Take Entry Test</button><p>{message}</p>
    {exam && <div><p>Time left: {timeLeft}s</p>{exam.questions.map((q) => <div key={q.id}><p>{q.question}</p>{q.options.map((op) => <button key={op} onClick={() => submitExam({ [q.id]: op })}>{op}</button>)}</div>)}</div>}
    {topics.map((t) => <details key={t.title}><summary>{t.title}</summary><p>{t.summary}</p><ul>{t.exercises.map((ex) => <li key={ex}>{ex}</li>)}</ul></details>)}
  </div>;
}

createRoot(document.getElementById('app')).render(<App />);
