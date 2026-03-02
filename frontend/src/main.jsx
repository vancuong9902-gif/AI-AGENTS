import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import './styles.css';

const api = axios.create({ baseURL: '/api', withCredentials: true });

function Alert({ type = 'info', msg }) {
  if (!msg) return null;
  return <div className={`alert alert-${type}`}>{msg}</div>;
}

function TopicCards({ topics }) {
  if (!topics.length) return null;
  return (
    <div className="stack">
      {topics.map((t) => (
        <div key={t.title} className="card topic-card">
          <strong>📘 {t.title}</strong>
          <p className="topic-summary">{t.summary}</p>
          <ul className="topic-exercises">
            {t.exercises.map((ex) => (
              <li key={ex}>{ex}</li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function StepIndicator({ steps }) {
  return (
    <div className="step-indicator" role="status" aria-live="polite">
      {steps.map((step) => (
        <div key={step.label} className={`step step-${step.state}`}>
          <span className="step-dot" />
          <span>{step.label}</span>
        </div>
      ))}
    </div>
  );
}

function HomePage() {
  const [health, setHealth] = React.useState('checking');
  const goTo = (path) => window.history.pushState({}, '', path);

  React.useEffect(() => {
    let mounted = true;
    fetch('/api/health')
      .then((res) => {
        if (!mounted) return;
        setHealth(res.ok ? 'online' : 'offline');
      })
      .catch(() => {
        if (!mounted) return;
        setHealth('offline');
      });

    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="shell">
      <h1>AI LMS Demo</h1>
      <div className="card auth-card stack">
        <p className="muted">Demo mode: no login required.</p>
        <p className={`health-pill ${health}`}>{health === 'online' ? '🟢 System Online' : health === 'offline' ? '🔴 Backend Offline' : '🟡 Checking system status...'}</p>
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
  const [feedback, setFeedback] = React.useState({ type: 'info', msg: '' });
  const [courseId, setCourseId] = React.useState(null);
  const [topics, setTopics] = React.useState([]);
  const [exam, setExam] = React.useState(null);
  const [timeLeft, setTimeLeft] = React.useState(600);
  const [loading, setLoading] = React.useState(false);
  const [studentCourseLoaded, setStudentCourseLoaded] = React.useState(false);
  const [currentQuestion, setCurrentQuestion] = React.useState(0);
  const [answers, setAnswers] = React.useState({});
  const [result, setResult] = React.useState(null);

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
    if (timeLeft === 0 && exam && path === '/student') submitExam(answers);
  }, [timeLeft]);

  const roleHeaders = React.useMemo(() => {
    if (path === '/teacher') return { 'X-User-Id': '1', 'X-User-Role': 'teacher' };
    return { 'X-User-Id': '2', 'X-User-Role': 'student' };
  }, [path]);

  function navTo(nextPath) {
    window.history.pushState({}, '', nextPath);
    setPath(nextPath);
    setFeedback({ type: 'info', msg: '' });
  }

  function levelClass(level) {
    const normalized = (level || '').toLowerCase();
    if (normalized.includes('advanced')) return 'level-advanced';
    if (normalized.includes('intermediate')) return 'level-intermediate';
    return 'level-beginner';
  }

  function resetDemo() {
    setCourseId(null);
    setTopics([]);
    setExam(null);
    setAnswers({});
    setResult(null);
    setCurrentQuestion(0);
    setStudentCourseLoaded(false);
    setTimeLeft(600);
    setFeedback({ type: 'success', msg: 'Demo reset - ready for new upload' });
  }

  async function withFeedback(action) {
    setLoading(true);
    setFeedback({ type: 'info', msg: '' });
    try {
      await action();
    } catch (error) {
      const msg = error?.response?.data?.error?.message || error?.message || 'Something went wrong.';
      setFeedback({ type: 'error', msg });
    } finally {
      setLoading(false);
    }
  }

  async function uploadPdf(e) {
    const file = e.target.files[0];
    if (!file) return;

    await withFeedback(async () => {
      const form = new FormData();
      form.append('file', file);
      const r = await api.post('/mvp/courses/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data', ...roleHeaders },
      });
      setCourseId(r.data.data.course_id);
      setTopics([]);
      setExam(null);
      setResult(null);
      setFeedback({ type: 'success', msg: '✅ PDF uploaded' });
    });
  }

  async function genTopics() {
    await withFeedback(async () => {
      const r = await api.post(`/mvp/courses/${courseId}/generate-topics`, {}, { headers: roleHeaders });
      setTopics(r.data.data.topics || []);
      setFeedback({ type: 'success', msg: '✅ Course topics generated' });
    });
  }

  async function genExam() {
    await withFeedback(async () => {
      const r = await api.post(`/mvp/courses/${courseId}/generate-entry-test`, {}, { headers: roleHeaders });
      setExam(r.data.data);
      setFeedback({ type: 'success', msg: '✅ Entry test ready' });
    });
  }

  async function loadStudentCourse() {
    await withFeedback(async () => {
      const r = await api.get('/mvp/student/course', { headers: roleHeaders });
      const fetchedTopics = r.data.data.topics || [];
      setTopics(fetchedTopics);
      setStudentCourseLoaded(Boolean(fetchedTopics.length));
      setResult(null);
      setFeedback({ type: fetchedTopics.length ? 'success' : 'info', msg: fetchedTopics.length ? '✅ Course loaded' : (r.data.data.message || 'No course available yet.') });
    });
  }

  async function loadStudentExam() {
    await withFeedback(async () => {
      const r = await api.get('/mvp/student/exams/latest', { headers: roleHeaders });
      setExam(r.data.data);
      setTimeLeft(r.data.data.duration_seconds);
      setCurrentQuestion(0);
      setAnswers({});
      setResult(null);
      setFeedback({ type: 'info', msg: 'Exam started. Good luck!' });
    });
  }

  async function submitExam(submittedAnswers) {
    if (!exam) return;
    await withFeedback(async () => {
      const r = await api.post(`/mvp/student/exams/${exam.exam_id}/submit`, { answers: submittedAnswers }, { headers: roleHeaders });
      setResult(r.data.data);
      setExam(null);
      setFeedback({ type: 'success', msg: '✅ Exam submitted successfully' });
    });
  }

  const studentSteps = [
    { label: 'Load Course', state: studentCourseLoaded ? 'done' : 'in-progress' },
    { label: 'Take Entry Test', state: exam ? 'in-progress' : result ? 'done' : studentCourseLoaded ? 'in-progress' : 'pending' },
    { label: 'Result', state: result ? 'done' : 'pending' },
  ];

  if (path === '/teacher') {
    return (
      <div className="shell stack">
        <h2>Teacher Dashboard</h2>
        <div className="row">
          <button className="ghost" onClick={() => navTo('/')}>Back to Home</button>
          <button className="warning" onClick={resetDemo}>🔄 Reset Demo</button>
        </div>
        <input type="file" accept="application/pdf" onChange={uploadPdf} />
        <div className="row">
          <button onClick={genTopics} disabled={!courseId || loading}>Generate Course</button>
          <button onClick={genExam} disabled={!courseId || loading}>Generate Entry Test</button>
        </div>
        {loading && <div className="loading">Loading...</div>}
        <Alert type={feedback.type} msg={feedback.msg} />
        <TopicCards topics={topics} />
      </div>
    );
  }

  if (path === '/student') {
    const question = exam?.questions?.[currentQuestion];
    const selectedOption = question ? answers[question.id] : '';

    return (
      <div className="shell stack">
        <h2>Student Dashboard</h2>
        <button className="ghost" onClick={() => navTo('/')}>Back to Home</button>

        <StepIndicator steps={studentSteps} />

        <div className="row">
          <button onClick={loadStudentCourse} disabled={loading || exam}>Load Course</button>
          {studentCourseLoaded && <button onClick={loadStudentExam} disabled={loading || exam}>Take Entry Test</button>}
        </div>

        {loading && <div className="loading">Loading...</div>}
        <Alert type={feedback.type} msg={feedback.msg} />

        {exam && question && (
          <div className="card exam-card stack">
            <p className="muted">Time left: {timeLeft}s</p>
            <p className="question-count">Question {currentQuestion + 1} of {exam.questions.length}</p>
            <p className="question-text">{question.question}</p>
            <div className="stack">
              {question.options.map((op) => (
                <button
                  key={op}
                  className={`option-btn ${selectedOption === op ? 'selected' : ''}`}
                  onClick={() => setAnswers((prev) => ({ ...prev, [question.id]: op }))}
                >
                  {op}
                </button>
              ))}
            </div>
            <div className="row">
              <button
                className="ghost"
                disabled={currentQuestion === 0}
                onClick={() => setCurrentQuestion((prev) => Math.max(prev - 1, 0))}
              >
                Previous
              </button>
              {currentQuestion < exam.questions.length - 1 ? (
                <button
                  disabled={!selectedOption}
                  onClick={() => setCurrentQuestion((prev) => Math.min(prev + 1, exam.questions.length - 1))}
                >
                  Next
                </button>
              ) : (
                <button disabled={Object.keys(answers).length !== exam.questions.length} onClick={() => submitExam(answers)}>
                  Submit Exam
                </button>
              )}
            </div>
          </div>
        )}

        {result && (
          <div className="card result-card stack">
            <h3>Final Score</h3>
            <p className="result-score">{result.score}</p>
            <p>
              Level: <span className={`badge ${levelClass(result.level)}`}>{result.level || 'Beginner'}</span>
            </p>
          </div>
        )}

        <TopicCards topics={topics} />
      </div>
    );
  }

  return <HomePage />;
}

createRoot(document.getElementById('app')).render(<App />);
