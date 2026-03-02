import React from 'react';
import Alert from '../components/Alert';
import { getErrorMessage, mvpApi } from '../api';

function formatTime(totalSeconds) {
  const mm = String(Math.floor(totalSeconds / 60)).padStart(2, '0');
  const ss = String(totalSeconds % 60).padStart(2, '0');
  return `${mm}:${ss}`;
}

function levelClass(level) {
  const normalized = String(level || '').toLowerCase();
  if (normalized.includes('advanced')) return 'level-advanced';
  if (normalized.includes('intermediate')) return 'level-intermediate';
  return 'level-beginner';
}

export default function StudentDashboard() {
  const [status, setStatus] = React.useState(null);
  const [checking, setChecking] = React.useState(false);
  const [course, setCourse] = React.useState(null);
  const [openTopics, setOpenTopics] = React.useState({});
  const [exam, setExam] = React.useState(null);
  const [questionIndex, setQuestionIndex] = React.useState(0);
  const [answers, setAnswers] = React.useState({});
  const [timer, setTimer] = React.useState(0);
  const [result, setResult] = React.useState(null);
  const [question, setQuestion] = React.useState('');
  const [conversation, setConversation] = React.useState([]);
  const [alert, setAlert] = React.useState({ type: 'info', message: '' });

  const loadStudentCourse = async () => {
    setAlert({ type: 'info', message: '' });
    try {
      const response = await mvpApi.getCourse();
      setCourse(response.data.data);
      setResult(null);
      setExam(null);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    }
  };

  const recheckStatus = async () => {
    setChecking(true);
    try {
      const response = await mvpApi.getStudentStatus();
      setStatus(response.data.data);
    } catch (_err) {
      // keep previous state
    } finally {
      setChecking(false);
    }
  };

  React.useEffect(() => {
    const init = async () => {
      setChecking(true);
      try {
        const response = await mvpApi.getStudentStatus();
        setStatus(response.data.data);
      } catch (err) {
        setAlert({ type: 'error', message: getErrorMessage(err) });
      } finally {
        setChecking(false);
      }
    };
    init();
  }, []);

  React.useEffect(() => {
    if (!exam) return;
    if (timer <= 0) return;
    const t = setInterval(() => setTimer((value) => value - 1), 1000);
    return () => clearInterval(t);
  }, [exam, timer]);

  React.useEffect(() => {
    if (exam && timer === 0) {
      submitExam();
    }
  }, [timer]);

  const startExam = async () => {
    setAlert({ type: 'info', message: '' });
    try {
      const response = await mvpApi.getLatestExam();
      const data = response.data.data;
      setExam(data);
      setTimer(data.duration_seconds || 600);
      setQuestionIndex(0);
      setAnswers({});
      setResult(null);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    }
  };

  const submitExam = async () => {
    if (!exam) return;
    try {
      const response = await mvpApi.submitExam(exam.exam_id, answers);
      setResult(response.data.data);
      setExam(null);
      setAlert({ type: 'success', message: 'Exam submitted.' });
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    }
  };

  const askTutor = async () => {
    if (!question.trim()) return;
    try {
      const userQuestion = question.trim();
      setQuestion('');
      const response = await mvpApi.askTutor(userQuestion);
      setConversation((prev) => [...prev, { role: 'user', text: userQuestion }, { role: 'bot', text: response.data.data.answer }]);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    }
  };

  const current = exam?.questions?.[questionIndex];
  const progress = exam ? ((questionIndex + 1) / exam.questions.length) * 100 : 0;

  const renderWaitingState = () => {
    if (!status || status.ready) return null;

    if (!status.has_course) {
      return (
        <div className="waiting-state">
          <div className="waiting-icon">🕐</div>
          <h3>Giáo viên chưa tải tài liệu lên</h3>
          <p>Vui lòng quay lại sau khi giáo viên chuẩn bị xong tài liệu học.</p>
          <button onClick={recheckStatus} disabled={checking}>{checking ? 'Đang kiểm tra...' : '🔄 Kiểm tra lại'}</button>
        </div>
      );
    }

    if (status.has_course && !status.has_topics) {
      return (
        <div className="waiting-state">
          <div className="waiting-icon">📄</div>
          <h3>Tài liệu đã được tải lên</h3>
          <p>Giáo viên đang chuẩn bị nội dung khoá học. Vui lòng chờ.</p>
          <button onClick={recheckStatus} disabled={checking}>{checking ? 'Đang kiểm tra...' : '🔄 Kiểm tra lại'}</button>
        </div>
      );
    }

    if (status.has_topics && !status.has_exam) {
      return (
        <div className="waiting-state">
          <div className="waiting-icon">📚</div>
          <h3>Nội dung khoá học đã sẵn sàng</h3>
          <p>Giáo viên chưa tạo bài kiểm tra đầu vào.</p>
          <div className="row waiting-actions">
            <button onClick={loadStudentCourse}>Xem tài liệu</button>
            <button disabled title="Chờ giáo viên tạo bài kiểm tra">Bài kiểm tra chưa sẵn sàng</button>
          </div>
          <button onClick={recheckStatus} disabled={checking}>{checking ? 'Đang kiểm tra...' : '🔄 Kiểm tra lại'}</button>
        </div>
      );
    }

    return null;
  };

  const waitingState = renderWaitingState();

  return (
    <div className="shell stack">
      <h1>Student Dashboard</h1>
      <Alert type={alert.type} message={alert.message} />

      {waitingState || (
        <>
          <section className="card stack">
            <h2>Course Content</h2>
            <button onClick={loadStudentCourse}>Load My Course</button>
            {!course?.topics?.length && course?.message && <p>{course.message}</p>}
            <div>
              {(course?.topics || []).map((topic, idx) => (
                <div key={topic.title} className={`accordion-item ${openTopics[idx] ? 'open' : ''}`}>
                  <div className="accordion-header" onClick={() => setOpenTopics((prev) => ({ ...prev, [idx]: !prev[idx] }))}>
                    <span>{topic.title}</span>
                    <span>{openTopics[idx] ? '−' : '+'}</span>
                  </div>
                  <div className="accordion-body">
                    <p>{topic.summary}</p>
                    <ul>{(topic.exercises || []).map((exercise) => <li key={exercise}>{exercise}</li>)}</ul>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {course && (
            <section className="card stack">
              <h2>Entry Test</h2>
              {!exam && <button onClick={startExam}>Start Entry Test</button>}
              {exam && current && (
                <div className="stack">
                  <div className="progress-bar"><div className="progress-fill" style={{ width: `${progress}%` }} /></div>
                  <p>Question {questionIndex + 1} / {exam.questions.length}</p>
                  <p className={`timer ${timer <= 60 ? 'urgent' : ''}`}>{formatTime(timer)}</p>
                  <h3>{current.question}</h3>
                  <div className="stack">
                    {current.options.map((option) => (
                      <label key={option} className="option-row">
                        <input
                          type="radio"
                          name={`q-${current.id}`}
                          checked={answers[current.id] === option}
                          onChange={() => setAnswers((prev) => ({ ...prev, [current.id]: option }))}
                        />
                        <span>{option}</span>
                      </label>
                    ))}
                  </div>
                  <div className="row">
                    <button disabled={questionIndex === 0} onClick={() => setQuestionIndex((v) => v - 1)}>Prev</button>
                    {questionIndex < exam.questions.length - 1 ? (
                      <button onClick={() => setQuestionIndex((v) => v + 1)}>Next</button>
                    ) : (
                      <button onClick={submitExam}>Submit</button>
                    )}
                  </div>
                </div>
              )}
              {result && (
                <div className="card stack">
                  <p>Score: {result.score}/10</p>
                  <span className={`badge ${levelClass(result.level)}`}>{result.level}</span>
                </div>
              )}
            </section>
          )}

          {course && (
            <section className="card stack">
              <h2>AI Tutor</h2>
              <div className="row">
                <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask a question about the course..." />
                <button onClick={askTutor}>Ask Tutor</button>
                <button className="ghost" onClick={() => setConversation([])}>Clear conversation</button>
              </div>
              <div className="chat-messages">
                {conversation.map((msg, idx) => (
                  <div key={idx} className={`chat-bubble ${msg.role === 'user' ? 'user' : 'bot'}`}>{msg.text}</div>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
