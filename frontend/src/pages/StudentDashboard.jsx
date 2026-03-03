import React from 'react';
import Alert from '../components/Alert';
import LoadingSpinner from '../components/LoadingSpinner';
import StudentProgressStepper from '../components/StudentProgressStepper';
import AssessmentTimer from '../components/AssessmentTimer';
import QuizQuestion from '../components/QuizQuestion';
import TutorChat from '../components/TutorChat';
import ResultPage from '../components/ResultPage';
import EmptyState from '../components/EmptyState';
import { mvpApi, getErrorMessage } from '../api';
import { useAuth } from '../auth';
import { ResponsiveContainer, RadialBarChart, RadialBar, PolarAngleAxis, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';

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



const EMPTY_CLASSROOM_TITLE = 'Lớp học chưa có tài liệu';
const EMPTY_CLASSROOM_DESCRIPTION = 'Giáo viên chưa tải lên tài liệu học. Vui lòng đợi thông báo từ giáo viên.';

function StudentFlowEmptyState({ onRefresh }) {
  return (
    <EmptyState
      icon="📚"
      title={EMPTY_CLASSROOM_TITLE}
      description={EMPTY_CLASSROOM_DESCRIPTION}
      action={<button className="sm" onClick={onRefresh}>Kiểm tra lại</button>}
    />
  );
}

function normalizeExamPayload(raw) {
  const data = raw?.data || raw;
  return {
    examId: data?.exam_id || data?.id,
    startedAt: data?.started_at,
    duration: data?.duration_seconds || 900,
    questions: (data?.questions || []).map((q, idx) => ({
      id: q.id ?? idx + 1,
      question: q.question || q.content || `Câu ${idx + 1}`,
      options: q.options || [],
      correct_answer: q.correct_answer,
      explanation: q.explanation,
      difficulty: q.difficulty || 'easy',
    })),
  };
}

function buildBreakdown(questions) {
  const map = { easy: [0, 0], medium: [0, 0], hard: [0, 0] };
  questions.forEach((q) => {
    const key = map[q.difficulty] ? q.difficulty : 'easy';
    map[key][1] += 1;
    if (q.selected_answer && q.selected_answer === q.correct_answer) map[key][0] += 1;
  });
  return map;
}

export default function StudentDashboard() {
  const { user } = useAuth();
  const [alert, setAlert] = React.useState({ type: 'info', message: '' });
  const [loading, setLoading] = React.useState(true);
  const [blockedByNoMaterial, setBlockedByNoMaterial] = React.useState(false);

  const [currentStep, setCurrentStep] = React.useState(1);
  const [completedSteps, setCompletedSteps] = React.useState([]);
  const [joinCode, setJoinCode] = React.useState('');
  const [classes, setClasses] = React.useState([]);
  const [selectedClass, setSelectedClass] = React.useState(null);
  const [subjects, setSubjects] = React.useState([]);
  const [selectedSubject, setSelectedSubject] = React.useState(null);

  const [placementExam, setPlacementExam] = React.useState(null);
  const [placementAnswers, setPlacementAnswers] = React.useState({});
  const [placementIndex, setPlacementIndex] = React.useState(0);
  const [placementResult, setPlacementResult] = React.useState(null);

  const [learningPlan, setLearningPlan] = React.useState(null);
  const [topicProgress, setTopicProgress] = React.useState({});

  const [finalExam, setFinalExam] = React.useState(null);
  const [finalAnswers, setFinalAnswers] = React.useState({});
  const [finalIndex, setFinalIndex] = React.useState(0);
  const [finalResult, setFinalResult] = React.useState(null);

  const completion = React.useMemo(() => {
    const topics = selectedSubject?.topics || [];
    if (!topics.length) return 0;
    const done = topics.filter((_, idx) => topicProgress[idx]).length;
    return Math.round((done / topics.length) * 100);
  }, [selectedSubject?.topics, topicProgress]);

  const markDone = (step) => {
    setCompletedSteps((prev) => (prev.includes(step) ? prev : [...prev, step]));
    setCurrentStep((prev) => Math.max(prev, step + 1));
  };

  const loadInitial = React.useCallback(async () => {
    setLoading(true);
    try {
      const [statusRes, classRes] = await Promise.all([
        mvpApi.getStudentStatus(),
        mvpApi.getMyClasses(),
      ]);
      const status = statusRes.data?.data || {};
      setBlockedByNoMaterial(!(status.has_course && status.has_topics));
      setClasses(classRes.data?.classrooms || classRes.data || []);
      const res = await mvpApi.getMyClasses();
      setMyClasses(res.data?.data?.items || res.data?.classrooms || res.data || []);
    } catch {
      setBlockedByNoMaterial(true);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadInitial();
  }, [loadInitial]);

  const handleJoin = async () => {
    try {
      await mvpApi.joinClassroom(joinCode.trim());
      setJoinCode('');
      await loadInitial();
      markDone(1);
      setAlert({ type: 'success', message: 'Đã tham gia lớp thành công.' });
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    }
  };

  const selectClass = async (cls) => {
    setSelectedClass(cls);
  const handleEnterClass = async (classroom) => {
    if (classroom?.has_content === false) {
      onCourseSelect({ classroom, topics: [] });
      return;
    }

    setLoading(true);
    try {
      const res = await mvpApi.getAvailableCourses();
      const rows = res.data?.courses || res.data?.data || res.data || [];
      setSubjects(rows.length ? rows : [{ ...cls, topics: [] }]);
      markDone(1);
      setCurrentStep(2);
    } catch {
      setSubjects([{ ...cls, topics: [] }]);
      setCurrentStep(2);
    }
  };

  const selectSubject = async (subject) => {
    setSelectedSubject(subject);
    markDone(2);
    setCurrentStep(3);
  };

  const startPlacement = async () => {
    try {
      const res = await mvpApi.getLatestExam();
      setPlacementExam(normalizeExamPayload(res.data));
      setPlacementAnswers({});
      setPlacementIndex(0);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    }
  };

  const submitPlacement = async () => {
    if (!placementExam?.examId) return;
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
      const res = await mvpApi.submitExam(placementExam.examId, placementAnswers);
      const data = res.data?.data || res.data;
      const mergedQuestions = placementExam.questions.map((q) => ({ ...q, selected_answer: placementAnswers[q.id] }));
      setPlacementResult({
        ...data,
        score: Number((data.score || 0) * 10),
        breakdown: buildBreakdown(mergedQuestions),
        questions: mergedQuestions,
      });
      markDone(3);
      markDone(4);
      setCurrentStep(5);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    }
  };

  const loadPlan = async () => {
    try {
      const res = await mvpApi.getLearningPlan(user?.id, selectedClass?.id);
      setLearningPlan(res.data?.plan || res.data || null);
      markDone(5);
      setCurrentStep(6);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    }
  };

  React.useEffect(() => {
    if (completion >= 80) {
      markDone(6);
      markDone(7);
      setCurrentStep(8);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [completion]);

  const startFinal = async () => {
    try {
      const courseId = selectedSubject?.course_id || selectedSubject?.id;
      const res = await mvpApi.getFinalExam(courseId);
      setFinalExam(normalizeExamPayload(res.data));
      setFinalAnswers({});
      setFinalIndex(0);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    }
  };

  const submitFinal = async () => {
    if (!finalExam?.examId) return;
    try {
      const res = await mvpApi.submitFinalExam(finalExam.examId, finalAnswers);
      const data = res.data?.data || res.data;
      const mergedQuestions = finalExam.questions.map((q) => ({ ...q, selected_answer: finalAnswers[q.id] }));
      setFinalResult({
        ...data,
        score: Number((data.score || 0) * 10),
        breakdown: buildBreakdown(mergedQuestions),
        questions: mergedQuestions,
      });
      markDone(8);
      markDone(9);
      setCurrentStep(9);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    }
  };

  const currentPlacementQuestion = placementExam?.questions?.[placementIndex];
  const currentFinalQuestion = finalExam?.questions?.[finalIndex];

  if (loading) {
    return <div className="shell"><LoadingSpinner label="Đang tải Student Flow..." /></div>;
  }

  if (blockedByNoMaterial) {
    return (
      <div className="shell">
        <div className="page-header">
          <h1>👨‍🎓 Trang học sinh</h1>
        </div>
        <div className="empty-state">
          <p>Lớp học chưa có tài liệu. Vui lòng chờ giáo viên tải lên tài liệu học.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="shell stack">
      <div className="page-header">
        <h1>👨‍🎓 Student Flow</h1>
        <p>Xin chào <strong>{user?.full_name || user?.email || 'học sinh'}</strong></p>
      </div>

      {alert.message && <Alert type={alert.type} message={alert.message} />}

      <StudentProgressStepper currentStep={currentStep} completedSteps={completedSteps} onStepClick={setCurrentStep} />

      {currentStep <= 1 && (
        <div className="card stack">
          <h3>Bước 1: Tham gia lớp</h3>
          <div className="row">
            <input value={joinCode} onChange={(e) => setJoinCode(e.target.value)} placeholder="Nhập invite_code" />
            <button onClick={handleJoin} disabled={!joinCode.trim()}>Tham gia lớp</button>
          </div>
          <div className="grid-3">
            {classes.map((cls) => (
              <button key={cls.id} className="card class-card" onClick={() => selectClass(cls)}>{cls.name}</button>
            ))}
          </div>
        </div>
      )}

      {currentStep === 2 && (
        <div className="card stack">
          <h3>Bước 2: Chọn môn học trong lớp {selectedClass?.name}</h3>
          <div className="grid-3">
            {subjects.map((sub) => (
              <button key={sub.id || sub.course_id} className="card class-card" onClick={() => selectSubject(sub)}>
                {sub.title || sub.name || 'Môn học'}
              </button>
            ))}
          </div>
      </div>
    </div>
  );
}



function TabProgress({ course }) {
  const [loading, setLoading] = React.useState(false);
  const [analytics, setAnalytics] = React.useState(null);

  React.useEffect(() => {
    const run = async () => {
      if (!course) return;
      setLoading(true);
      try {
        const res = await mvpApi.getStudentAnalytics();
        setAnalytics(res.data || null);
      } catch {
        setAnalytics(null);
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [course]);

  if (!course) {
    return <div className="empty-state"><div className="empty-icon">📈</div><p>Hãy chọn môn học để xem tiến độ.</p></div>;
  }

  if (loading) return <LoadingSpinner label="Đang tải student dashboard..." />;
  if (!analytics) return <div className="empty-state"><p>Chưa có dữ liệu analytics cá nhân.</p></div>;

  const radialData = [{ name: 'Progress', value: Number(analytics.overall_progress || 0), fill: '#4f46e5' }];
  const topicProgress = analytics.topic_progress || [];
  const scoreHistory = analytics.score_history || [];

  return (
    <div className="stack">
      <div className="grid-2">
        <div className="card">
          <div className="card-title">Tiến độ học tập tổng thể</div>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <RadialBarChart innerRadius="60%" outerRadius="100%" data={radialData} startAngle={180} endAngle={0}>
                <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
                <RadialBar dataKey="value" background cornerRadius={10} />
                <Tooltip />
              </RadialBarChart>
            </ResponsiveContainer>
          </div>
          <div className="row-between"><span>Overall</span><strong>{Number(analytics.overall_progress || 0).toFixed(1)}%</strong></div>
        </div>

        <div className="card">
          <div className="card-title">Giờ học tuần này</div>
          <div className="stat-value">{Number(analytics.study_hours_this_week || 0).toFixed(1)}h</div>
          <div className="card-sub">Tổng số giờ bạn đã học trong 7 ngày gần nhất.</div>
        </div>
      </div>

      <div className="card">
        <div className="card-title">Lịch sử điểm kiểm tra</div>
        <div className="chart-container">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={scoreHistory}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" />
              <YAxis domain={[0, 100]} />
              <Tooltip />
              <Area type="monotone" dataKey="score" stroke="#10b981" fill="#bbf7d0" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {currentStep === 3 && (
        <div className="stack">
          <div className="card row-between">
            <h3>Bước 3: Kiểm tra đầu vào</h3>
            {!placementExam ? <button onClick={startPlacement}>Bắt đầu bài kiểm tra</button> : (
              <AssessmentTimer
                durationSeconds={placementExam.duration}
                serverStartedAt={placementExam.startedAt}
                onExpire={submitPlacement}
                answers={placementAnswers}
                backupKey="placement-answers"
              />
            )}
          </div>

          {placementExam && currentPlacementQuestion && (
            <QuizQuestion
              question={currentPlacementQuestion}
              answered={{ selected: placementAnswers[currentPlacementQuestion.id] }}
              onAnswer={(opt) => setPlacementAnswers((prev) => ({ ...prev, [currentPlacementQuestion.id]: opt }))}
              showExplanation={false}
              onPrev={() => setPlacementIndex((v) => Math.max(0, v - 1))}
              onNext={() => setPlacementIndex((v) => Math.min(placementExam.questions.length - 1, v + 1))}
              onSubmit={submitPlacement}
              isFirst={placementIndex === 0}
              isLast={placementIndex === placementExam.questions.length - 1}
            />
          )}
        </div>
      )}

      {currentStep === 5 && placementResult && (
        <ResultPage
          title="Bước 4: Kết quả đầu vào"
          result={placementResult}
          questions={placementResult.questions}
          onViewRoadmap={loadPlan}
          onRetry={() => {
            setPlacementResult(null);
            setCurrentStep(3);
          }}
        />
      )}

      {currentStep === 6 && (
        <div className="stack">
          <div className="card stack">
            <h3>Bước 5-6: Lộ trình và học topic</h3>
            {learningPlan?.level && <div className="badge blue">Level: {learningPlan.level}</div>}
            <div className="badge orange">Tiến độ: {completion}%</div>
            {(selectedSubject?.topics || []).map((topic, idx) => (
              <div key={idx} className="topic-row">
                <div>
                  <strong>{topic.title || `Topic ${idx + 1}`}</strong>
                  <p>Đọc tài liệu → làm bài tập → hỏi tutor AI</p>
                </div>
                <button className={topicProgress[idx] ? 'success-btn sm' : 'sm'} onClick={() => setTopicProgress((prev) => ({ ...prev, [idx]: !prev[idx] }))}>
                  {topicProgress[idx] ? 'Đã xong' : 'Đánh dấu hoàn thành'}
                </button>
              </div>
            ))}
          </div>

          <TutorChat topicTitle={selectedSubject?.topics?.[0]?.title || 'chủ đề hiện tại'} sessionKey={`${selectedClass?.id || 'class'}-${user?.id || 'user'}`} />
        </div>
      )}

      {currentStep === 8 && (
        <div className="stack">
          <div className="card row-between">
            <h3>Bước 7-8: Mở khóa và thi cuối kỳ</h3>
            {!finalExam ? <button className="success-btn" onClick={startFinal}>Bắt đầu thi cuối kỳ</button> : (
              <AssessmentTimer
                durationSeconds={finalExam.duration}
                serverStartedAt={finalExam.startedAt}
                onExpire={submitFinal}
                answers={finalAnswers}
                backupKey="final-answers"
              />
            )}
          </div>

          {finalExam && currentFinalQuestion && (
            <QuizQuestion
              question={currentFinalQuestion}
              answered={{ selected: finalAnswers[currentFinalQuestion.id] }}
              onAnswer={(opt) => setFinalAnswers((prev) => ({ ...prev, [currentFinalQuestion.id]: opt }))}
              showExplanation={false}
              onPrev={() => setFinalIndex((v) => Math.max(0, v - 1))}
              onNext={() => setFinalIndex((v) => Math.min(finalExam.questions.length - 1, v + 1))}
              onSubmit={submitFinal}
              isFirst={finalIndex === 0}
              isLast={finalIndex === finalExam.questions.length - 1}
            />
          )}
        </div>
      )}

      {currentStep >= 9 && finalResult && (
        <ResultPage
          title="Bước 9: Kết quả cuối kỳ + AI đánh giá"
          result={finalResult}
          questions={finalResult.questions}
      <div className="card">
        <div className="card-title">Tiến độ theo từng topic</div>
        {topicProgress.length === 0 ? <div className="empty-state"><p>Chưa có dữ liệu topic.</p></div> : (
          <div className="stack">
            {topicProgress.map((t) => (
              <div key={t.topic}>
                <div className="row-between"><span>{t.topic}</span><span>{Number(t.score || 0).toFixed(1)}%</span></div>
                <div className="progress-bar"><div className="progress-fill" style={{ width: `${Math.max(0, Math.min(100, Number(t.score || 0)))}%` }} /></div>
              </div>
            ))}
          </div>
        )}
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
    if (selectedCourse?.classroom?.has_content === false) {
      setView('empty');
      return;
    }
    setView('dashboard');
    setTab('content');
  };

  const clearAlert = () => setAlert({ type: 'info', message: '' });

  const isCurrentClassEmpty = course?.classroom?.has_content === false;
  const [view, setView] = React.useState('dashboard');

  const refresh = React.useCallback(async () => {
    setGuardLoading(true);
    try {
      const res = await mvpApi.getStudentStatus();
      const d = res.data.data || {};
      const hasContent = Boolean(d.has_content ?? (d.has_course && d.has_topics));
      setBlockedByNoMaterial(!hasContent);
      setView(hasContent ? 'dashboard' : 'empty');
    } catch {
      setBlockedByNoMaterial(true);
      setView('empty');
    } finally {
      setGuardLoading(false);
    }
  }, []);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  React.useEffect(() => {
    if (isCurrentClassEmpty) {
      setView('empty');
      return;
    }
    if (!blockedByNoMaterial) {
      setView('dashboard');
    }
  }, [blockedByNoMaterial, isCurrentClassEmpty]);

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
              if ((blockedByNoMaterial || view === 'empty' || isCurrentClassEmpty) && item.key !== 'courses') return;
              setTab(item.key);
              clearAlert();
            }}
            disabled={(blockedByNoMaterial || view === 'empty' || isCurrentClassEmpty) && item.key !== 'courses'}
          >
            {item.label}
          </button>
        ))}
      </div>


      {guardLoading ? (
        <LoadingSpinner label="Đang kiểm tra dữ liệu khóa học..." />
      ) : (view === 'empty' || blockedByNoMaterial || isCurrentClassEmpty) ? (
        <StudentFlowEmptyState onRefresh={refresh} />
      ) : null}

      {tab === 'courses' && (
        <TabCourses
          setAlert={setAlert}
          onCourseSelect={onCourseSelect}
        />
      )}

      {view !== 'empty' && !blockedByNoMaterial && tab === 'content' && (
        <TabContent
          course={course}
        />
      )}

      {view !== 'empty' && !blockedByNoMaterial && tab === 'exams' && (
        <TabExams
          course={course}
          setAlert={setAlert}
        />
      )}

      {view !== 'empty' && !blockedByNoMaterial && tab === 'homework' && (
        <TabHomework
          course={course}
          setAlert={setAlert}
        />
      )}

      {view !== 'empty' && !blockedByNoMaterial && tab === 'progress' && (
        <TabProgress
          course={course}
        />
      )}

      {view !== 'empty' && !blockedByNoMaterial && tab === 'tutor' && (
        <TabTutor
          course={course}
        />
      )}
    </div>
  );
}
