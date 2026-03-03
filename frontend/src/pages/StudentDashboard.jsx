import React from 'react';
import Alert from '../components/Alert';
import LoadingSpinner from '../components/LoadingSpinner';
import { mvpApi, getErrorMessage } from '../api';
import { useAuth } from '../auth';

function formatTime(totalSeconds) {
  const m = String(Math.floor(totalSeconds / 60)).padStart(2, '0');
  const s = String(totalSeconds % 60).padStart(2, '0');
  return `${m}:${s}`;
}

function levelClass(level) {
  const normalized = String(level || '').toLowerCase();
  if (normalized.includes('advanced')) return 'level-advanced';
  if (normalized.includes('intermediate')) return 'level-intermediate';
  return 'level-beginner';
}

function levelVN(level) {
  const normalized = String(level || '').toLowerCase();
  if (normalized.includes('advanced')) return '⭐ Nâng cao';
  if (normalized.includes('intermediate')) return '📘 Trung bình';
  return '📗 Cơ bản';
}

function normalizeExamPayload(raw) {
  const data = raw?.data || raw;
  const questions = (data?.questions || []).map((q, idx) => ({
    id: q.id ?? q.question_id ?? idx + 1,
    question: q.question || q.stem || q.content || `Câu hỏi ${idx + 1}`,
    options: q.options || q.choices || [],
    difficulty: q.difficulty || q.level || 'easy',
  }));

  return {
    exam_id: data?.exam_id || data?.id,
    duration_seconds: data?.duration_seconds || data?.duration || 600,
    questions,
  };
}

function ExamView({ exam, onSubmit, submitLabel }) {
  const [index, setIndex] = React.useState(0);
  const [answers, setAnswers] = React.useState({});
  const [timer, setTimer] = React.useState(exam?.duration_seconds || 600);
  const [submitting, setSubmitting] = React.useState(false);

  const total = exam?.questions?.length || 0;
  const current = exam?.questions?.[index] || null;
  const answeredCount = Object.keys(answers).length;
  const progress = total ? ((index + 1) / total) * 100 : 0;

  const handleSubmit = React.useCallback(async () => {
    if (submitting || !exam?.exam_id) return;
    setSubmitting(true);
    try {
      await onSubmit(exam.exam_id, answers);
    } finally {
      setSubmitting(false);
    }
  }, [answers, exam, onSubmit, submitting]);

  React.useEffect(() => {
    if (!exam?.exam_id) return;
    if (timer <= 0) {
      handleSubmit();
      return;
    }

    const intervalId = setInterval(() => {
      setTimer((prev) => prev - 1);
    }, 1000);

    return () => clearInterval(intervalId);
  }, [exam, handleSubmit, timer]);

  if (!exam || !total) {
    return (
      <div className="empty-state">
        <div className="empty-icon">📝</div>
        <p>Không có dữ liệu bài kiểm tra.</p>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="card">
        <div className="row-between">
          <div className="row">
            <span className="badge gray">Câu {index + 1}/{total}</span>
            <span className="badge blue">Đã trả lời: {answeredCount}/{total}</span>
          </div>
          <div className={`timer-box ${timer <= 60 ? 'urgent' : ''}`}>
            ⏱ <span className={`timer ${timer <= 60 ? 'urgent' : ''}`}>{formatTime(timer)}</span>
          </div>
        </div>

        <div className="progress-bar" style={{ marginTop: 12 }}>
          <div className="progress-fill" style={{ width: `${progress}%` }} />
        </div>
      </div>

      {current && (
        <div className="card stack">
          <div className="row-between">
            <span className={`badge ${current.difficulty === 'hard' ? 'level-advanced' : current.difficulty === 'medium' ? 'level-intermediate' : 'level-beginner'}`}>
              {current.difficulty === 'hard' ? '🔴 Khó' : current.difficulty === 'medium' ? '🟡 Trung bình' : '🟢 Dễ'}
            </span>
          </div>

          <h3 style={{ lineHeight: 1.6 }}>{current.question}</h3>

          <div className="stack" style={{ gap: 8 }}>
            {current.options.map((opt, i) => (
              <div
                key={`${current.id}-${i}`}
                className={`option-row ${answers[current.id] === opt ? 'selected' : ''}`}
                onClick={() => setAnswers((prev) => ({ ...prev, [current.id]: opt }))}
              >
                <span style={{ fontWeight: 700, minWidth: 20 }}>{String.fromCharCode(65 + i)}.</span>
                <span>{opt}</span>
              </div>
            ))}
          </div>

          <div className="row-between">
            <button className="ghost sm" onClick={() => setIndex((v) => v - 1)} disabled={index === 0}>
              ← Câu trước
            </button>

            {index < total - 1 ? (
              <button className="sm" onClick={() => setIndex((v) => v + 1)}>
                Câu tiếp →
              </button>
            ) : (
              <button className="success-btn" onClick={handleSubmit} disabled={submitting}>
                {submitting ? '⏳ Đang nộp...' : submitLabel}
              </button>
            )}
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-title" style={{ marginBottom: 10 }}>Nhảy nhanh đến câu</div>
        <div className="row" style={{ gap: 6 }}>
          {exam.questions.map((q, idx) => {
            let buttonClass = 'sm ghost';
            if (answers[q.id]) buttonClass = 'sm success-btn';
            if (idx === index) buttonClass = 'sm';
            return (
              <button
                key={q.id}
                className={buttonClass}
                style={{ minWidth: 34, padding: '5px 8px' }}
                onClick={() => setIndex(idx)}
              >
                {idx + 1}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function TabCourses({ setAlert, onCourseSelect }) {
  const { user } = useAuth();
  const [loading, setLoading] = React.useState(false);
  const [joining, setJoining] = React.useState(false);
  const [joinCode, setJoinCode] = React.useState('');
  const [myClasses, setMyClasses] = React.useState([]);

  const loadMyClasses = React.useCallback(async () => {
    setLoading(true);
    try {
      const res = await mvpApi.getMyClasses();
      setMyClasses(res.data?.data?.items || res.data?.classrooms || res.data || []);
    } catch {
      setMyClasses([]);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    if (!user?.id) return;
    loadMyClasses();
  }, [loadMyClasses, user?.id]);

  const handleJoinClass = async () => {
    if (!joinCode.trim()) return;

    setJoining(true);
    try {
      await mvpApi.joinClassroom(joinCode.trim());
      setJoinCode('');
      setAlert({ type: 'success', message: '✅ Tham gia lớp học thành công!' });
      await loadMyClasses();
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setJoining(false);
    }
  };

  const handleEnterClass = async (classroom) => {
    setLoading(true);
    try {
      const res = await mvpApi.getCourse();
      const course = res.data.data || res.data;

      if (!course || !Array.isArray(course.topics) || course.topics.length === 0) {
        setAlert({ type: 'warning', message: '⚠️ Giáo viên chưa tải tài liệu' });
        return;
      }

      onCourseSelect({ ...course, classroom });
      setAlert({ type: 'success', message: `✅ Đã vào lớp "${classroom?.name || 'Môn học'}"` });
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="stack">
      <h2 style={{ fontSize: 18 }}>📚 Môn học</h2>

      <div className="card">
        <div className="card-title" style={{ marginBottom: 12 }}>🔑 Tham gia lớp bằng mã code</div>
        <div className="row">
          <input
            placeholder="Nhập mã lớp (VD: ABC123)"
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleJoinClass()}
            style={{ maxWidth: 260 }}
          />
          <button onClick={handleJoinClass} disabled={!joinCode.trim() || joining}>
            {joining ? '⏳ Đang tham gia...' : '➕ Tham gia lớp'}
          </button>
        </div>
      </div>

      {loading ? (
        <LoadingSpinner label="Đang tải lớp học..." />
      ) : myClasses.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🏫</div>
          <p>Bạn chưa tham gia lớp nào. Hãy nhập mã lớp để bắt đầu.</p>
        </div>
      ) : (
        <div className="grid-3">
          {myClasses.map((cls) => (
            <div className="card" key={cls.id}>
              <div className="card-header">
                <div>
                  <div className="card-title">🏫 {cls.name}</div>
                  {cls.invite_code && <span className="badge blue">Mã: {cls.invite_code}</span>}
                </div>
              </div>

              <p style={{ color: 'var(--gray-500)', marginBottom: 12 }}>
                {cls.description || 'Lớp học chưa có mô tả.'}
              </p>

              <div className="row student-class-meta">
                <span className="badge gray">Môn học: {cls.course_id || 'N/A'}</span>
                <span className="badge green">Tiến độ: {Math.round(cls.progress_percent || 0)}%</span>
                <span className="badge blue">Điểm: {cls.score ?? '-'}</span>
              </div>
              <button className="sm" onClick={() => handleEnterClass(cls)}>
                📖 Vào học
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TabContent({ course }) {
  const { user } = useAuth();
  const [opened, setOpened] = React.useState({});

  React.useEffect(() => {
    if (!user?.id) return;
  }, [user?.id]);

  if (!course) {
    return (
      <div className="empty-state">
        <div className="empty-icon">📖</div>
        <p>Vui lòng chọn môn học ở tab "📚 Môn học" trước.</p>
      </div>
    );
  }

  if (!course.topics || course.topics.length === 0) {
    return (
      <div className="alert warning">
        ⚠️ Giáo viên chưa tải tài liệu
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="row-between">
        <h2 style={{ fontSize: 18 }}>📖 Bài học</h2>
        <span className="badge blue">{course.topics.length} chủ đề</span>
      </div>

      {course.topics.map((topic, index) => (
        <div key={`${topic.title}-${index}`} className={`accordion-item ${opened[index] ? 'open' : ''}`}>
          <div className="accordion-header" onClick={() => setOpened((prev) => ({ ...prev, [index]: !prev[index] }))}>
            <span>📌 {topic.title || `Chủ đề ${index + 1}`}</span>
            <span className="accordion-chevron">▼</span>
          </div>

          <div className="accordion-body">
            <p style={{ marginTop: 10, color: 'var(--gray-600)' }}>{topic.summary || 'Chưa có tóm tắt.'}</p>

            {Array.isArray(topic.exercises) && topic.exercises.length > 0 && (
              <div style={{ marginTop: 10 }}>
                <div className="card-sub" style={{ marginBottom: 6 }}>📝 Bài tập gợi ý</div>
                <ul className="task-list">
                  {topic.exercises.map((exercise, exIdx) => (
                    <li key={`${topic.title}-${exIdx}`}>{exercise}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function TabExams({ course, setAlert }) {
  const { user } = useAuth();
  const [mode, setMode] = React.useState('menu');
  const [loading, setLoading] = React.useState(false);
  const [exam, setExam] = React.useState(null);
  const [entryResult, setEntryResult] = React.useState(null);
  const [finalResult, setFinalResult] = React.useState(null);

  const hasCourse = Boolean(course && Array.isArray(course.topics) && course.topics.length > 0);

  React.useEffect(() => {
    if (!user?.id) return;
  }, [user?.id]);

  const startEntryExam = async () => {
    setLoading(true);
    try {
      const res = await mvpApi.getLatestExam();
      setExam(normalizeExamPayload(res.data));
      setMode('entry_exam');
      setEntryResult(null);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  const submitEntryExam = async (examId, answers) => {
    try {
      const res = await mvpApi.submitExam(examId, answers);
      const data = res.data.data || res.data;
      setEntryResult(data);
      setMode('entry_result');
      setAlert({ type: 'success', message: '✅ Nộp bài kiểm tra đầu vào thành công.' });
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    }
  };

  const startFinalExam = async () => {
    if (!course) return;

    setLoading(true);
    try {
      const courseId = course.course_id || course.id;
      const res = await mvpApi.getFinalExam(courseId);
      setExam(normalizeExamPayload(res.data));
      setMode('final_exam');
      setFinalResult(null);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  const submitFinalExam = async (examId, answers) => {
    try {
      const res = await mvpApi.submitFinalExam(examId, answers);
      const data = res.data.data || res.data;
      setFinalResult(data);
      setMode('final_result');
      setAlert({ type: 'success', message: '✅ Đã nộp bài thi cuối kỳ.' });
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    }
  };

  if (!hasCourse) {
    return (
      <div className="stack">
        <div className="alert warning">
          ⚠️ Giáo viên chưa tải tài liệu, chưa có bài kiểm tra
        </div>
      </div>
    );
  }

  if (mode === 'entry_exam') {
    return (
      <div className="stack">
        <div className="row-between">
          <h2 style={{ fontSize: 18 }}>📝 Kiểm tra đầu vào</h2>
          <button className="ghost sm" onClick={() => setMode('menu')}>← Quay lại</button>
        </div>

        <ExamView exam={exam} onSubmit={submitEntryExam} submitLabel="✅ Nộp bài đầu vào" />
      </div>
    );
  }

  if (mode === 'final_exam') {
    return (
      <div className="stack">
        <div className="row-between">
          <h2 style={{ fontSize: 18 }}>🎓 Kiểm tra cuối kỳ</h2>
          <button className="ghost sm" onClick={() => setMode('menu')}>← Quay lại</button>
        </div>

        <ExamView exam={exam} onSubmit={submitFinalExam} submitLabel="✅ Nộp bài cuối kỳ" />
      </div>
    );
  }

  if (mode === 'entry_result' && entryResult) {
    return (
      <div className="stack">
        <h2 style={{ fontSize: 18 }}>🎯 Kết quả kiểm tra đầu vào</h2>
        <div className="card" style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 56, marginBottom: 8 }}>{entryResult.score >= 8 ? '🏆' : entryResult.score >= 5 ? '👍' : '📚'}</div>
          <div className="card-value">{entryResult.score}/10</div>
          <span className={`badge ${levelClass(entryResult.level)}`}>{levelVN(entryResult.level)}</span>
          <p style={{ marginTop: 12, color: 'var(--gray-500)' }}>{entryResult.message || 'AI đã phân tích trình độ của bạn.'}</p>
        </div>
        <button onClick={() => setMode('menu')}>← Về danh sách kiểm tra</button>
      </div>
    );
  }

  if (mode === 'final_result' && finalResult) {
    return (
      <div className="stack">
        <h2 style={{ fontSize: 18 }}>🎓 Kết quả kiểm tra cuối kỳ</h2>
        <div className="card" style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 56, marginBottom: 8 }}>{finalResult.score >= 8 ? '🥇' : finalResult.score >= 6 ? '🥈' : '🥉'}</div>
          <div className="card-value">{finalResult.score}/10</div>
          <span className={`badge ${levelClass(finalResult.level)}`}>{levelVN(finalResult.level)}</span>
          <p style={{ marginTop: 12, color: 'var(--gray-500)' }}>{finalResult.message || 'Đây là kết quả bài thi cuối kỳ của bạn.'}</p>
        </div>
        <button onClick={() => setMode('menu')}>← Về danh sách kiểm tra</button>
      </div>
    );
  }

  return (
    <div className="stack">
      <h2 style={{ fontSize: 18 }}>📝 Kiểm tra</h2>

      <div className="grid-2">
        <div className="card stack">
          <div style={{ fontSize: 34, textAlign: 'center' }}>📋</div>
          <div className="card-title" style={{ textAlign: 'center' }}>Kiểm tra đầu vào</div>
          <p style={{ color: 'var(--gray-500)', textAlign: 'center' }}>
            Làm bài kiểm tra để AI phân tích trình độ ban đầu của bạn.
          </p>
          {entryResult && (
            <div className="alert success">
              Điểm gần nhất: <strong>{entryResult.score}/10</strong> · {levelVN(entryResult.level)}
            </div>
          )}
          <button onClick={startEntryExam} disabled={loading}>
            {loading ? '⏳ Đang tải đề...' : entryResult ? '🔄 Làm lại bài đầu vào' : '▶️ Bắt đầu bài đầu vào'}
          </button>
        </div>

        <div className="card stack" style={{ border: '1.5px solid var(--warning)' }}>
          <div style={{ fontSize: 34, textAlign: 'center' }}>🎓</div>
          <div className="card-title" style={{ textAlign: 'center' }}>Kiểm tra cuối kỳ</div>
          <p style={{ color: 'var(--gray-500)', textAlign: 'center' }}>
            Đề cuối kỳ độc lập với đề đầu vào, bao phủ toàn bộ kiến thức đã học.
          </p>
          {finalResult && (
            <div className="alert success">
              Điểm gần nhất: <strong>{finalResult.score}/10</strong> · {levelVN(finalResult.level)}
            </div>
          )}
          <button className="success-btn" onClick={startFinalExam} disabled={loading}>
            {loading ? '⏳ Đang tải đề...' : '🎓 Bắt đầu thi cuối kỳ'}
          </button>
        </div>
      </div>
    </div>
  );
}

function TabHomework({ course, setAlert }) {
  const { user } = useAuth();
  const [loading, setLoading] = React.useState(false);
  const [plan, setPlan] = React.useState(null);
  const [answers, setAnswers] = React.useState({});
  const [submittingTaskId, setSubmittingTaskId] = React.useState(null);
  const [submissionResult, setSubmissionResult] = React.useState({});

  const loadPlan = React.useCallback(async () => {
    if (!user?.id) return;

    setLoading(true);
    try {
      const classroomId = course?.classroom?.id;
      const res = await mvpApi.getLearningPlan(user.id, classroomId);
      setPlan(res.data?.plan || res.data || null);
    } catch {
      setPlan(null);
    } finally {
      setLoading(false);
    }
  }, [course?.classroom?.id, user?.id]);

  React.useEffect(() => {
    loadPlan();
  }, [loadPlan]);

  const tasks = plan?.tasks || plan?.homework_tasks || [];

  const handleSubmitTask = async (task) => {
    const text = answers[task.id]?.trim();
    if (!text || !user?.id) return;

    setSubmittingTaskId(task.id);
    try {
      const res = await mvpApi.submitHomeworkAnswer(task.id, text, user.id);
      setSubmissionResult((prev) => ({ ...prev, [task.id]: res.data }));
      setAlert({ type: 'success', message: '✅ Đã nộp bài tập.' });
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setSubmittingTaskId(null);
    }
  };

  if (!course) {
    return (
      <div className="empty-state">
        <div className="empty-icon">✏️</div>
        <p>Vui lòng vào tab "📚 Môn học" để chọn lớp trước khi làm bài tập.</p>
      </div>
    );
  }

  if (loading) {
    return <LoadingSpinner label="Đang tải bài tập AI giao..." />;
  }

  return (
    <div className="stack">
      <div className="row-between">
        <h2 style={{ fontSize: 18 }}>✏️ Bài tập</h2>
        {plan?.level && <span className="badge orange">Trình độ: {levelVN(plan.level)}</span>}
      </div>

      {tasks.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📝</div>
          <p>Chưa có bài tập được giao. Hãy làm bài kiểm tra đầu vào trước.</p>
        </div>
      ) : (
        tasks.map((task, idx) => (
          <div className="card stack" key={task.id || idx}>
            <div className="row-between">
              <div>
                <div className="card-title">{task.title || task.topic_title || `Bài tập ${idx + 1}`}</div>
                {task.topic_name && <div className="card-sub">📌 {task.topic_name}</div>}
              </div>
              <span className={`badge ${task.completed ? 'green' : 'gray'}`}>
                {task.completed ? '✓ Hoàn thành' : '⏳ Chưa làm'}
              </span>
            </div>

            <p style={{ color: 'var(--gray-600)' }}>
              {task.description || task.content || 'Làm bài tập theo hướng dẫn của AI.'}
            </p>

            {submissionResult[task.id] ? (
              <div className="alert success">
                ✅ Điểm: <strong>{submissionResult[task.id].score ?? submissionResult[task.id].grade ?? 'N/A'}</strong>
                {submissionResult[task.id].feedback && <div>{submissionResult[task.id].feedback}</div>}
              </div>
            ) : (
              <>
                <textarea
                  value={answers[task.id] || ''}
                  onChange={(e) => setAnswers((prev) => ({ ...prev, [task.id]: e.target.value }))}
                  placeholder="Nhập câu trả lời của bạn..."
                  style={{ minHeight: 110 }}
                />

                <div className="row">
                  <button
                    className="success-btn"
                    onClick={() => handleSubmitTask(task)}
                    disabled={!answers[task.id]?.trim() || submittingTaskId === task.id}
                  >
                    {submittingTaskId === task.id ? '⏳ Đang nộp...' : '📤 Nộp bài'}
                  </button>
                </div>
              </>
            )}
          </div>
        ))
      )}
    </div>
  );
}

function TabTutor({ course }) {
  const { user } = useAuth();
  const [question, setQuestion] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [messages, setMessages] = React.useState([]);
  const endRef = React.useRef(null);

  React.useEffect(() => {
    if (!user?.id) return;
  }, [user?.id]);

  React.useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const suggestions = (course?.topics || []).slice(0, 4).map((t) => `Giải thích giúp em chủ đề: ${t.title}`);

  const handleAskTutor = async () => {
    if (!question.trim() || loading) return;

    const q = question.trim();
    setQuestion('');
    setMessages((prev) => [...prev, { role: 'user', text: q }]);
    setLoading(true);

    try {
      const res = await mvpApi.askTutor(q);
      const answer = res.data?.data?.answer || res.data?.data?.message || 'Xin lỗi, tôi chưa có câu trả lời phù hợp.';
      setMessages((prev) => [...prev, { role: 'bot', text: answer }]);
    } catch {
      setMessages((prev) => [...prev, { role: 'bot', text: '⚠️ Kết nối tới AI Tutor thất bại. Vui lòng thử lại.' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="stack">
      <div className="row-between">
        <h2 style={{ fontSize: 18 }}>🤖 AI Tutor</h2>
        {messages.length > 0 && <button className="ghost sm" onClick={() => setMessages([])}>🗑 Xóa hội thoại</button>}
      </div>

      <div className="card" style={{ background: 'var(--primary-light)' }}>
        <p style={{ color: 'var(--gray-700)' }}>
          AI Tutor sẽ hỗ trợ bạn theo nội dung môn học. Hãy đặt câu hỏi rõ ràng để nhận câu trả lời tốt hơn.
        </p>

        {suggestions.length > 0 && (
          <div className="row" style={{ marginTop: 8 }}>
            {suggestions.map((s, idx) => (
              <button key={idx} className="ghost sm" onClick={() => setQuestion(s)}>💬 {s}</button>
            ))}
          </div>
        )}
      </div>

      <div className="chat-box">
        <div className="chat-messages">
          {messages.length === 0 && (
            <div className="chat-bubble bot">
              👋 Xin chào! Mình là AI Tutor. Bạn có thể hỏi về bài học, bài tập hoặc kiến thức trong khóa học.
            </div>
          )}

          {messages.map((m, idx) => (
            <div key={idx} className={`chat-bubble ${m.role}`}>
              {m.text}
            </div>
          ))}

          {loading && <div className="chat-bubble bot typing">⏳ Đang trả lời...</div>}
          <div ref={endRef} />
        </div>

        <div className="chat-input-row">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleAskTutor()}
            placeholder="Nhập câu hỏi cho AI Tutor..."
            disabled={loading}
          />
          <button onClick={handleAskTutor} disabled={!question.trim() || loading}>
            {loading ? '⏳' : '➤ Gửi'}
          </button>
        </div>
      </div>
    </div>
  );
}



function TabProgress({ course }) {
  const { user } = useAuth();
  const [loading, setLoading] = React.useState(false);
  const [data, setData] = React.useState(null);

  React.useEffect(() => {
    const run = async () => {
      if (!course?.classroom?.id || !user?.id) return;
      setLoading(true);
      try {
        const res = await mvpApi.getStudentProgress(user.id, course.classroom.id);
        setData(res.data.data || null);
      } catch {
        setData(null);
      }
      setLoading(false);
    };
    run();
  }, [course?.classroom?.id, user?.id]);

  if (!course) {
    return <div className="empty-state"><div className="empty-icon">📈</div><p>Hãy chọn môn học để xem tiến độ.</p></div>;
  }

  if (loading) return <LoadingSpinner label="Đang tải tiến độ..." />;

  const topics = data?.topics_progress || [];
  const sessions = data?.study_sessions || [];
  const streak = data?.streak_days || 0;
  const totalHours = data?.total_hours || 0;
  const cmp = data?.comparison_with_class_avg || { student_avg: 0, class_avg: 0 };

  const byDay = {};
  sessions.forEach((s) => {
    const d = s.date;
    if (!d) return;
    byDay[d] = (byDay[d] || 0) + Number(s.duration_seconds || 0);
  });

  const days = Array.from({ length: 30 }, (_, i) => {
    const dt = new Date(Date.now() - (29 - i) * 86400000);
    const key = dt.toISOString().slice(0, 10);
    const sec = byDay[key] || 0;
    let cls = 'heat-0';
    if (sec > 3600 * 2) cls = 'heat-4';
    else if (sec > 3600) cls = 'heat-3';
    else if (sec > 1800) cls = 'heat-2';
    else if (sec > 0) cls = 'heat-1';
    return { key, cls };
  });

  return (
    <div className="stack">
      <div className="card">
        <div className="row-between">
          <div className="card-title">🔥 Bạn đã học {streak} ngày liên tiếp</div>
          <span className="badge blue">Tổng giờ học: {totalHours}h</span>
        </div>
      </div>

      <div className="card">
        <div className="card-title">Tiến độ theo chủ đề</div>
        {topics.length === 0 ? <div className="empty-state"><p>Chưa có dữ liệu chủ đề.</p></div> : (
          <div className="stack">
            {topics.map((t) => (
              <div key={t.topic_id}>
                <div className="row-between"><span>{t.title}</span><span>{t.progress_pct}%</span></div>
                <div className="progress-bar"><div className="progress-fill" style={{ width: `${t.progress_pct}%` }} /></div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-title">Calendar heatmap (30 ngày)</div>
        <div className="heatmap-grid">
          {days.map((d) => <div key={d.key} className={`heat-cell ${d.cls}`} title={d.key} />)}
        </div>
      </div>

      <div className="card">
        <div className="card-title">So sánh với trung bình lớp</div>
        <div className="stack">
          <div>
            <div className="row-between"><span>Điểm của bạn</span><span>{cmp.student_avg}</span></div>
            <div className="progress-bar"><div className="progress-fill" style={{ width: `${Math.max(0, Math.min(100, cmp.student_avg))}%` }} /></div>
          </div>
          <div>
            <div className="row-between"><span>Trung bình lớp</span><span>{cmp.class_avg}</span></div>
            <div className="progress-bar"><div className="progress-fill" style={{ width: `${Math.max(0, Math.min(100, cmp.class_avg))}%` }} /></div>
          </div>
        </div>
      </div>
    </div>
  );
}

const TABS = [
  { key: 'courses', label: '📚 Môn học' },
  { key: 'content', label: '📖 Bài học' },
  { key: 'exams', label: '📝 Kiểm tra' },
  { key: 'homework', label: '✏️ Bài tập' },
  { key: 'progress', label: '📈 Tiến độ học tập' },
  { key: 'tutor', label: '🤖 AI Tutor' },
];

export default function StudentDashboard() {
  const { user } = useAuth();
  const [tab, setTab] = React.useState('courses');
  const [alert, setAlert] = React.useState({ type: 'info', message: '' });
  const [course, setCourse] = React.useState(null);
  const [guardLoading, setGuardLoading] = React.useState(true);
  const [blockedByNoMaterial, setBlockedByNoMaterial] = React.useState(false);

  const onCourseSelect = (selectedCourse) => {
    setCourse(selectedCourse);
    setTab('content');
  };

  const clearAlert = () => setAlert({ type: 'info', message: '' });


  React.useEffect(() => {
    const loadStatus = async () => {
      setGuardLoading(true);
      try {
        const res = await mvpApi.getStudentStatus();
        const d = res.data.data || {};
        const hasMaterial = Boolean(d.has_course && d.has_topics);
        setBlockedByNoMaterial(!hasMaterial);
      } catch {
        setBlockedByNoMaterial(true);
      } finally {
        setGuardLoading(false);
      }
    };
    loadStatus();
  }, []);

  return (
    <div className="shell">
      <div className="page-header">
        <h1>👨‍🎓 Trang học sinh</h1>
        <p>
          Xin chào, <strong>{user?.full_name || user?.email || 'Học sinh'}</strong>
          {course && <> · Đang học: <strong>{course?.classroom?.name || 'Môn học hiện tại'}</strong></>}
        </p>
      </div>

      {alert.message && (
        <div style={{ marginBottom: 16 }}>
          <Alert type={alert.type} message={alert.message} />
        </div>
      )}

      <div className="tabs">
        {TABS.map((item) => (
          <button
            key={item.key}
            className={`tab ${tab === item.key ? 'active' : ''}`}
            onClick={() => {
              if (blockedByNoMaterial && item.key !== 'courses') return;
              setTab(item.key);
              clearAlert();
            }}
            disabled={blockedByNoMaterial && item.key !== 'courses'}
          >
            {item.label}
          </button>
        ))}
      </div>


      {guardLoading ? (
        <LoadingSpinner label="Đang kiểm tra dữ liệu khóa học..." />
      ) : blockedByNoMaterial ? (
        <div className="alert warning">
          📚 Giáo viên chưa tải tài liệu. Vui lòng chờ giáo viên chuẩn bị khóa học.
        </div>
      ) : null}

      {tab === 'courses' && (
        <TabCourses
          setAlert={setAlert}
          onCourseSelect={onCourseSelect}
        />
      )}

      {!blockedByNoMaterial && tab === 'content' && (
        <TabContent
          course={course}
        />
      )}

      {!blockedByNoMaterial && tab === 'exams' && (
        <TabExams
          course={course}
          setAlert={setAlert}
        />
      )}

      {!blockedByNoMaterial && tab === 'homework' && (
        <TabHomework
          course={course}
          setAlert={setAlert}
        />
      )}

      {!blockedByNoMaterial && tab === 'progress' && (
        <TabProgress
          course={course}
        />
      )}

      {!blockedByNoMaterial && tab === 'tutor' && (
        <TabTutor
          course={course}
        />
      )}
    </div>
  );
}
