import React from 'react';
import Alert from '../components/Alert';
import LoadingSpinner from '../components/LoadingSpinner';
import StudentProgressStepper from '../components/StudentProgressStepper';
import AssessmentTimer from '../components/AssessmentTimer';
import QuizQuestion from '../components/QuizQuestion';
import TutorChat from '../components/TutorChat';
import ResultPage from '../components/ResultPage';
import { mvpApi, getErrorMessage } from '../api';
import { useAuth } from '../auth';

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
        />
      )}
    </div>
  );
}
