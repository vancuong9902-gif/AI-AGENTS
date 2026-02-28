import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Modal from '../ui/Modal';
import Banner from '../ui/Banner';
import PageHeader from '../ui/PageHeader';
import { apiJson } from '../lib/api';

// OLD: const QUESTIONS = [...] (hardcode quiz tĩnh) đã được thay bằng flow gọi API thật.

const toneByDifficulty = {
  easy: '#16a34a',
  medium: '#2563eb',
  hard: '#dc2626',
};

function normalizeQuestion(question) {
  return {
    ...question,
    question_id: question?.question_id ?? question?.id,
    options: Array.isArray(question?.options) ? question.options : [],
    type: question?.type || 'mcq',
  };
}

function classification(scorePercent = 0) {
  if (scorePercent >= 85) return { label: 'Giỏi', tone: 'success' };
  if (scorePercent >= 70) return { label: 'Khá', tone: 'info' };
  if (scorePercent >= 50) return { label: 'Trung bình', tone: 'warning' };
  return { label: 'Yếu', tone: 'danger' };
}

export default function Quiz() {
  const navigate = useNavigate();
  const userId = Number(localStorage.getItem('user_id') || 1);
  const classroomId = Number(localStorage.getItem('classroom_id') || 1);

  const [quizData, setQuizData] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [timeLeftSec, setTimeLeftSec] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [startedAt, setStartedAt] = useState(null);
  const [openConfirm, setOpenConfirm] = useState(false);

  const autoSubmitRef = useRef(false);
  const timerRef = useRef(null);

  const fmtTime = (sec) => {
    const s = Math.max(0, sec || 0);
    const mm = String(Math.floor(s / 60)).padStart(2, '0');
    const ss = String(s % 60).padStart(2, '0');
    return `${mm}:${ss}`;
  };

  const loadQuiz = async () => {
    setLoading(true);
    setError('');
    try {
      const myPath = await apiJson(`/lms/student/${userId}/my-path`);
      const planQuizId = myPath?.placement_quiz_id || myPath?.quiz_id || myPath?.assigned_tasks?.[0]?.quiz_id;

      let quizId = planQuizId;
      if (!quizId) {
        const assessments = await apiJson(`/assessments?kind=placement&classroom_id=${classroomId}`);
        const list = Array.isArray(assessments) ? assessments : assessments?.items || assessments?.assessments || [];
        if (list.length > 0) {
          const latest = [...list].sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime())[0];
          quizId = latest?.quiz_id || latest?.id;
        }
      }

      if (!quizId) {
        throw new Error('Chưa có bài kiểm tra đầu vào cho lớp của bạn.');
      }

      const detail = await apiJson(`/assessments/${quizId}`);
      const normalizedQuestions = (detail?.questions || []).map(normalizeQuestion);
      const totalSec = (detail?.time_limit_minutes || 30) * 60;

      setQuizData(detail);
      setQuestions(normalizedQuestions);
      setTimeLeftSec(totalSec);
      setStartedAt(Date.now());
    } catch (e) {
      setError(e?.message || 'Không tải được bài quiz');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadQuiz();
    return () => clearInterval(timerRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = async (isAutoSubmit = false) => {
    if (submitting || !quizData?.quiz_id) return;
    clearInterval(timerRef.current);
    setSubmitting(true);
    setError('');

    const elapsed = Math.round((Date.now() - (startedAt || Date.now())) / 1000);
    const answerList = questions.map((q) => ({
      question_id: q.question_id,
      selected_option: q.type === 'mcq' ? (answers[q.question_id] ?? null) : null,
      text_answer: q.type === 'essay' ? (answers[q.question_id] ?? null) : null,
    }));

    try {
      const res = await apiJson(`/assessments/${quizData.quiz_id}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          duration_sec: elapsed,
          answers: answerList,
          auto_submitted: isAutoSubmit,
        }),
      });
      setResult(res);

      await apiJson(`/lms/student/${userId}/assign-learning-path`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          quiz_id: quizData.quiz_id,
          student_level: res?.student_level || res?.classify,
          document_ids: quizData?.document_ids || (quizData?.document_id ? [quizData.document_id] : []),
          classroom_id: quizData?.classroom_id || classroomId,
        }),
      });
    } catch (e) {
      setError(e?.message || 'Lỗi khi nộp bài');
    } finally {
      setSubmitting(false);
      setOpenConfirm(false);
    }
  };

  useEffect(() => {
    if (timeLeftSec === null || result) return undefined;
    timerRef.current = setInterval(() => {
      setTimeLeftSec((prev) => {
        if (prev <= 1) {
          clearInterval(timerRef.current);
          if (!autoSubmitRef.current) {
            autoSubmitRef.current = true;
            handleSubmit(true);
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timerRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeLeftSec !== null, !!result]);

  const answeredCount = useMemo(() => Object.values(answers).filter((v) => v !== null && `${v}`.trim() !== '').length, [answers]);
  const timeWarn = (timeLeftSec || 0) < 300;

  const scorePercent = Number(result?.score_percent || 0);
  const classInfo = classification(scorePercent);
  const duration = Number(result?.duration_sec || 0);
  const correctCount = Number(result?.correct_count || 0);
  const byTopic = result?.breakdown_by_topic || result?.breakdown?.by_topic || {};
  const byDifficulty = result?.breakdown_by_difficulty || result?.breakdown?.by_difficulty || {};

  return (
    <div className='container grid-12'>
      <Card className='span-12'>
        <PageHeader
          title='Bài kiểm tra đầu vào'
          subtitle='Hệ thống chấm tự động và tạo lộ trình học cá nhân hoá.'
          breadcrumbs={['Học sinh', 'Quiz đầu vào']}
          right={<Banner tone={timeWarn ? 'danger' : 'info'}><span style={timeWarn ? { animation: 'pulse 1.2s infinite' } : {}}>⏱ {fmtTime(timeLeftSec)}</span></Banner>}
        />
      </Card>

      {loading ? <Card className='span-12'>Đang tải câu hỏi...</Card> : null}
      {error ? (
        <Card className='span-12 stack-sm'>
          <Banner tone='danger'>{error}</Banner>
          {!submitting ? <Button onClick={loadQuiz}>Thử lại</Button> : null}
        </Card>
      ) : null}

      {!loading && !result && questions.length > 0 ? (
        <Card className='span-12 stack-md'>
          <div><strong>Đã trả lời:</strong> {answeredCount}/{questions.length} câu</div>
          <div style={{ height: 8, background: '#e2e8f0', borderRadius: 999 }}>
            <div style={{ height: 8, width: `${Math.round((answeredCount / Math.max(1, questions.length)) * 100)}%`, background: '#2563eb', borderRadius: 999 }} />
          </div>

          {questions.map((q, idx) => (
            <div key={q.question_id || idx} className='ui-card'>
              <div className='row'>
                <strong>Câu {idx + 1}</strong>
                <span style={{ color: toneByDifficulty[q.difficulty] || '#334155' }}>
                  {q.difficulty || 'medium'} · {q.topic || 'Chung'}
                </span>
              </div>
              <p>{q.stem}</p>
              {q.type === 'essay' ? (
                <textarea
                  rows={4}
                  style={{ width: '100%' }}
                  placeholder='Nhập câu trả lời của bạn...'
                  value={answers[q.question_id] || ''}
                  onChange={(e) => setAnswers((prev) => ({ ...prev, [q.question_id]: e.target.value }))}
                />
              ) : (
                <div className='stack-sm'>
                  {q.options.map((op, i) => {
                    const selected = answers[q.question_id] === i;
                    return (
                      <label key={`${q.question_id}-${i}`} style={{ padding: 8, borderRadius: 8, background: selected ? '#dbeafe' : 'transparent' }}>
                        <input
                          type='radio'
                          name={`q-${q.question_id}`}
                          checked={selected}
                          onChange={() => setAnswers((prev) => ({ ...prev, [q.question_id]: i }))}
                        /> {op}
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          ))}

          <div className='row'>
            <Button variant='primary' disabled={submitting} onClick={() => setOpenConfirm(true)}>{submitting ? 'Đang nộp...' : 'Nộp bài'}</Button>
          </div>
        </Card>
      ) : null}

      {result ? (
        <Card className='span-12 stack-sm'>
          <h2 className='section-title'>Kết quả bài làm</h2>
          <Banner tone={classInfo.tone}>Điểm: <strong>{scorePercent}%</strong> · Xếp loại: <strong>{classInfo.label}</strong></Banner>
          <p>Thời gian làm bài: {Math.floor(duration / 60)} phút {duration % 60} giây</p>
          <p>Số câu đúng: {correctCount}/{questions.length}</p>

          <h3>Breakdown theo chủ đề</h3>
          <table>
            <thead><tr><th>Chủ đề</th><th>Điểm</th><th>Nhận xét</th></tr></thead>
            <tbody>
              {Object.entries(byTopic).map(([topic, data]) => {
                const pct = Number(data?.percent || 0);
                const note = pct >= 80 ? 'Tốt' : pct >= 60 ? 'Ổn' : 'Cần ôn lại';
                return <tr key={topic}><td>{topic}</td><td>{pct}%</td><td>{note}</td></tr>;
              })}
            </tbody>
          </table>

          <p>
            Breakdown độ khó: Dễ {byDifficulty.easy?.correct || 0}/{byDifficulty.easy?.total || 0} · Trung bình {byDifficulty.medium?.correct || 0}/{byDifficulty.medium?.total || 0} · Khó {byDifficulty.hard?.correct || 0}/{byDifficulty.hard?.total || 0}
          </p>

          <Button variant='primary' onClick={() => navigate('/learning-path')}>Xem lộ trình học cá nhân hoá →</Button>
        </Card>
      ) : null}

      <Modal
        open={openConfirm}
        title='Xác nhận nộp bài'
        onClose={() => setOpenConfirm(false)}
        actions={(
          <>
            <Button onClick={() => setOpenConfirm(false)}>Huỷ</Button>
            <Button variant='primary' onClick={() => handleSubmit(false)} disabled={submitting}>{submitting ? 'Đang nộp...' : 'Xác nhận nộp'}</Button>
          </>
        )}
      >
        Bạn chắc chắn muốn nộp bài ngay bây giờ?
      </Modal>
    </div>
  );
}
