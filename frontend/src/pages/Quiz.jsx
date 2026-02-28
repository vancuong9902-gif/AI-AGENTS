import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Modal from '../ui/Modal';
import Banner from '../ui/Banner';
import PageHeader from '../ui/PageHeader';
import { apiJson } from '../lib/api';
import { useExamTimer } from '../hooks/useExamTimer';

function normalizeOption(option, index) {
  if (typeof option === 'string') return { value: index, label: option };
  return {
    value: option?.id ?? option?.value ?? option?.key ?? index,
    label: option?.label ?? option?.text ?? option?.content ?? `Lựa chọn ${index + 1}`,
  };
}

function normalizeQuestion(question, index) {
  return {
    question_id: Number(question?.question_id ?? question?.id ?? index + 1),
    topic: question?.topic || question?.topic_name || 'Chung',
    stem: question?.stem || question?.question_text || question?.content || `Câu hỏi ${index + 1}`,
    options: (Array.isArray(question?.options) ? question.options : []).map(normalizeOption),
  };
}

export default function Quiz() {
  const { quizSetId } = useParams();
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [started, setStarted] = useState(false);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [openConfirm, setOpenConfirm] = useState(false);
  const [questions, setQuestions] = useState([]);
  const [durationSec, setDurationSec] = useState(0);
  const [startInfo, setStartInfo] = useState(null);
  const [answers, setAnswers] = useState({});
  const [submitted, setSubmitted] = useState(false);
  const [result, setResult] = useState(null);
  const autoSubmitRef = useRef(false);

  const answeredCount = useMemo(
    () => Object.values(answers).filter((value) => value !== undefined && value !== null).length,
    [answers],
  );
  const allAnswered = questions.length > 0 && answeredCount === questions.length;

  const initialTimeLeft = useMemo(() => {
    if (!startInfo?.deadline) return 0;
    const lagBuffer = Math.max(0, Number(startInfo?.clientLagSeconds || 0) > 5 ? Number(startInfo.clientLagSeconds) : 0);
    return Math.max(0, Math.floor((new Date(startInfo.deadline).getTime() - Date.now()) / 1000 + lagBuffer));
  }, [startInfo]);

  const handleSubmit = useCallback(
    async (autoSubmit = false) => {
      if (!quizSetId || submitted || submitting || !started) return;
      if (!autoSubmit && !allAnswered) {
        setError('Bạn cần trả lời đủ câu hỏi trước khi nộp bài.');
        return;
      }

      setSubmitting(true);
      setError('');
      try {
        const payload = {
          user_id: Number(localStorage.getItem('user_id') || 0),
          duration_sec: Math.max(0, durationSec - initialTimeLeft),
          answers: questions.map((question) => ({
            question_id: Number(question.question_id),
            answer_index: answers[question.question_id] ?? null,
            answer_text: null,
          })),
        };

        const response = await apiJson(`/v1/assessments/quiz-sets/${encodeURIComponent(quizSetId)}/submit`, {
          method: 'POST',
          body: payload,
        });
        setResult({ ...response, autoSubmitted: autoSubmit });
        setSubmitted(true);
      } catch (submitError) {
        setError(submitError?.message || 'Nộp bài thất bại.');
      } finally {
        setSubmitting(false);
        setOpenConfirm(false);
      }
    },
    [allAnswered, answers, durationSec, initialTimeLeft, questions, quizSetId, started, submitted, submitting],
  );

  const { formattedTime, warningLevel } = useExamTimer({
    totalSeconds: started && !submitted ? initialTimeLeft : 0,
    onTimeUp: () => {
      if (!autoSubmitRef.current) {
        autoSubmitRef.current = true;
        handleSubmit(true);
      }
    },
    onWarning: (secsLeft) => {
      console.info(`Còn ${secsLeft} giây!`);
    },
  });

  const loadQuiz = useCallback(async () => {
    if (!quizSetId) {
      setError('Không tìm thấy quizSetId trên URL.');
      setLoading(false);
      return;
    }

    setLoading(true);
    setError('');
    try {
      const response = await apiJson(`/v1/assessments/${encodeURIComponent(quizSetId)}`);
      const normalizedQuestions = (Array.isArray(response?.questions) ? response.questions : []).map(normalizeQuestion);
      if (!normalizedQuestions.length) throw new Error('Bộ đề chưa có câu hỏi.');

      const apiTime = Number(response?.time_limit_minutes || 0) * 60;
      const fallback = Number(response?.duration_seconds || 0);
      const resolvedDuration = apiTime > 0 ? apiTime : fallback;
      if (!resolvedDuration) throw new Error('Không xác định được thời lượng bài kiểm tra.');

      setQuestions(normalizedQuestions);
      setDurationSec(Math.floor(resolvedDuration));
    } catch (e) {
      setError(e?.message || 'Không thể tải bộ câu hỏi.');
    } finally {
      setLoading(false);
    }
  }, [quizSetId]);

  const startQuiz = useCallback(async () => {
    if (!quizSetId || started) return;
    setStarting(true);
    setError('');
    const requestStart = Date.now();
    try {
      const startResp = await apiJson(`/v1/assessments/quiz-sets/${encodeURIComponent(quizSetId)}/start`, { method: 'POST' });
      const requestEnd = Date.now();
      const networkLagSeconds = Math.max(0, (requestEnd - requestStart) / 1000);
      setStartInfo({ ...startResp, clientLagSeconds: networkLagSeconds });
      setStarted(true);
      autoSubmitRef.current = false;
    } catch (e) {
      setError(e?.message || 'Không thể bắt đầu bài kiểm tra.');
    } finally {
      setStarting(false);
    }
  }, [quizSetId, started]);

  useEffect(() => {
    loadQuiz();
  }, [loadQuiz]);

  const timerBanner = useMemo(() => {
    if (!started) return <Banner tone='info'>⏱ Nhấn “Bắt đầu làm bài” để khởi chạy đồng hồ.</Banner>;
    if (warningLevel === 'critical') {
      return <Banner tone='error'><span className='exam-timer-pulse'>🔴 CÒN {formattedTime} – Nộp bài ngay!</span></Banner>;
    }
    if (warningLevel === 'warning') {
      return <Banner tone='warning'>⚠️ Còn {formattedTime} – Hãy kiểm tra lại bài!</Banner>;
    }
    return <Banner tone='info'>⏱ Thời gian: {formattedTime}</Banner>;
  }, [formattedTime, started, warningLevel]);
import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import Card from '../ui/Card'
import Button from '../ui/Button'
import Modal from '../ui/Modal'
import Banner from '../ui/Banner'
import Badge from '../ui/Badge'
import Spinner from '../ui/Spinner'
import PageHeader from '../ui/PageHeader'
import { apiJson } from '../lib/api'

const DIFFICULTY_LABEL = {
  easy: 'Dễ',
  medium: 'Trung bình',
  hard: 'Khó',
}

const DIFFICULTY_TONE = {
  easy: 'success',
  medium: 'warning',
  hard: 'danger',
}

const CLASSIFICATION_LABEL = {
  gioi: 'GIỎI',
  kha: 'KHÁ',
  trung_binh: 'TRUNG BÌNH',
  yeu: 'YẾU',
}

const CLASSIFICATION_COLOR = {
  gioi: '#22c55e',
  kha: '#3b82f6',
  trung_binh: '#f59e0b',
  yeu: '#ef4444',
}

const OPTION_LABELS = ['A', 'B', 'C', 'D', 'E', 'F']

function formatTime(secs) {
  const safeSecs = Math.max(0, Number(secs) || 0)
  const m = Math.floor(safeSecs / 60).toString().padStart(2, '0')
  const s = (safeSecs % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}

function getTimerTone(timeLeft) {
  if (timeLeft < 60) return 'danger'
  if (timeLeft < 300) return 'warning'
  return 'success'
}

function isAnswered(question, value) {
  if (question?.type === 'essay') {
    return typeof value === 'string' && value.trim().length > 0
  }
  return typeof value === 'number'
}

export default function Quiz() {
  const { quizSetId } = useParams()
  const navigate = useNavigate()
  const { userId } = useAuth()

  const [quizSet, setQuizSet] = useState(null)
  const [questions, setQuestions] = useState([])
  const [answers, setAnswers] = useState({})
  const [timeLeft, setTimeLeft] = useState(0)
  const [phase, setPhase] = useState('loading')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0)
  const [topicExpanded, setTopicExpanded] = useState(false)

  const timerRef = useRef(null)
  const autoSubmitRef = useRef(false)
  const startTimeRef = useRef(null)

  const answeredCount = questions.reduce((count, question) => {
    const answer = answers[question.id]
    return count + (isAnswered(question, answer) ? 1 : 0)
  }, 0)

  const activeQuestion = questions[currentQuestionIndex] || null

  const loadQuizSet = useCallback(async () => {
    if (!quizSetId) {
      setError('Không tìm thấy quizSetId trên URL.')
      setPhase('result')
      return
    }

    setPhase('loading')
    setError(null)
    setResult(null)

    try {
      const data = await apiJson(`/v1/assessments/quiz-sets/${encodeURIComponent(quizSetId)}`)
      setQuizSet(data)
      setTimeLeft(Number(data?.duration_seconds) || 0)
      setPhase('instructions')
    } catch (err) {
      setError(err?.message || 'Không thể tải thông tin bài quiz.')
      setPhase('result')
    }
  }, [quizSetId])

  const handleSubmit = useCallback(async (autoSubmitted = false) => {
    if (!quizSetId || phase === 'submitting' || phase === 'result') return

    setPhase('submitting')
    setError(null)

    try {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }

      const elapsed = Math.max(
        0,
        Math.floor((Date.now() - (startTimeRef.current || Date.now())) / 1000),
      )

      const payload = {
        answers,
        time_taken_seconds: elapsed,
        auto_submitted: autoSubmitted,
      }

      const submitData = await apiJson(
        `/v1/assessments/quiz-sets/${encodeURIComponent(quizSetId)}/submit`,
        {
          method: 'POST',
          body: payload,
        },
      )

      setResult(submitData)
      setPhase('result')
      setConfirmOpen(false)
    } catch (err) {
      setError(err?.message || 'Nộp bài thất bại.')
      setPhase('active')
    }
  }, [answers, phase, quizSetId])

  const startQuiz = useCallback(async () => {
    if (!quizSetId) return

    setPhase('loading')
    setError(null)

    try {
      const data = await apiJson(
        `/v1/assessments/quiz-sets/${encodeURIComponent(quizSetId)}/questions`,
      )
      const rows = Array.isArray(data) ? data : []

      setQuestions(rows)
      setAnswers({})
      setCurrentQuestionIndex(0)
      setTimeLeft(Number(quizSet?.duration_seconds) || 0)
      autoSubmitRef.current = false
      startTimeRef.current = Date.now()
      setPhase('active')
    } catch (err) {
      setError(err?.message || 'Không thể tải câu hỏi quiz.')
      setPhase('instructions')
    }
  }, [quizSet?.duration_seconds, quizSetId])

  useEffect(() => {
    loadQuizSet()
  }, [loadQuizSet])

  useEffect(() => {
    if (phase !== 'active') return
    timerRef.current = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(timerRef.current)
          autoSubmitRef.current = true
          handleSubmit(true)
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => clearInterval(timerRef.current)
  }, [phase, handleSubmit])

  const handleSelectMcq = (questionId, optionIndex) => {
    setAnswers((prev) => ({ ...prev, [questionId]: optionIndex }))
  }

  const handleEssayChange = (questionId, value) => {
    setAnswers((prev) => ({ ...prev, [questionId]: value }))
  }

  const distribution = quizSet?.difficulty_distribution || { easy: 0, medium: 0, hard: 0 }
  const percentage = Number(result?.percentage) || 0
  const classification = result?.classification || 'trung_binh'

  return (
    <div className='container grid-12'>
      <Card className='span-12'>
        <PageHeader
          title='Placement Quiz / Diagnostic Pre'
          subtitle='Làm bài kiểm tra đầu vào để hệ thống đánh giá năng lực ban đầu.'
          breadcrumbs={['Học sinh', 'Diagnostic Pre']}
          right={timerBanner}
        />
      </Card>

      {loading ? <Card className='span-12'><Banner tone='info'>Đang tải bài kiểm tra...</Banner></Card> : null}
      {!loading && error ? <Card className='span-12'><Banner tone='error'>{error}</Banner></Card> : null}

      {!loading && !error && !started ? (
        <Card className='span-12 stack-sm'>
          <Banner tone='info'>Bài có {questions.length} câu hỏi · Thời lượng {Math.floor(durationSec / 60)} phút.</Banner>
          <Button variant='primary' onClick={startQuiz} disabled={starting}>{starting ? 'Đang bắt đầu...' : 'Bắt đầu làm bài'}</Button>
        </Card>
      ) : null}

      {!loading && !error && started && questions.length > 0 ? (
        <Card className='span-12 stack-md'>
          <Banner tone={allAnswered ? 'success' : 'warning'}>
            Đã trả lời {answeredCount}/{questions.length} câu
          </Banner>

          {questions.map((question, index) => (
            <div key={question.question_id} className='ui-card stack-sm'>
              <strong>Câu {index + 1}</strong>
              <p style={{ margin: 0 }}>{question.stem}</p>
              <div className='stack-sm'>
                {question.options.map((option) => (
                  <label key={`${question.question_id}-${option.value}`}>
                    <input
                      type='radio'
                      name={`question-${question.question_id}`}
                      checked={answers[question.question_id] === option.value}
                      disabled={submitted || submitting}
                      onChange={() => setAnswers((prev) => ({ ...prev, [question.question_id]: option.value }))}
                    /> {option.label}
                  </label>
                ))}
              </div>
            </div>
          ))}

          <Button variant='primary' onClick={() => setOpenConfirm(true)} disabled={submitted || submitting || !allAnswered}>
            {submitting ? 'Đang nộp...' : 'Nộp bài'}
          </Button>
        </Card>
      ) : null}

      {result ? <Card className='span-12'><Banner tone='success'>Điểm: {result?.score_percent ?? 0}{result.autoSubmitted ? ' · Tự động nộp do hết giờ' : ''}</Banner></Card> : null}
          title={quizSet?.title || 'Placement Quiz'}
          subtitle={`Xin chào ${userId || ''}, hoàn thành bài quiz để hệ thống đánh giá đúng năng lực.`}
          breadcrumbs={['Học sinh', 'Quiz đánh giá']}
          right={
            phase === 'active' ? (
              <Banner tone={getTimerTone(timeLeft)}>⏱ {formatTime(timeLeft)}</Banner>
            ) : null
          }
        />
      </Card>

      {error ? (
        <Card className='span-12'>
          <Banner tone='danger'>{error}</Banner>
        </Card>
      ) : null}

      {phase === 'loading' ? (
        <Card className='span-12'>
          <div className='row' style={{ gap: 10 }}>
            <Spinner />
            <span>Đang tải dữ liệu bài quiz...</span>
          </div>
        </Card>
      ) : null}

      {phase === 'instructions' && quizSet ? (
        <Card className='span-12 stack-md'>
          <h3 style={{ margin: 0 }}>{quizSet.title}</h3>
          <div className='row' style={{ gap: 16, flexWrap: 'wrap' }}>
            <span>Tổng số câu: <strong>{quizSet.question_count || 0}</strong></span>
            <span>Thời gian: <strong>{Math.floor((quizSet.duration_seconds || 0) / 60)} phút</strong></span>
          </div>

          <div className='row' style={{ gap: 8, flexWrap: 'wrap' }}>
            <Badge tone='success'>Easy: {distribution.easy || 0}</Badge>
            <Badge tone='warning'>Medium: {distribution.medium || 0}</Badge>
            <Badge tone='danger'>Hard: {distribution.hard || 0}</Badge>
          </div>

          <Banner tone='info'>{quizSet.instructions || 'Đọc kỹ đề trước khi bắt đầu làm bài.'}</Banner>

          <div className='row'>
            <Button variant='primary' onClick={startQuiz}>Bắt đầu làm bài →</Button>
          </div>
        </Card>
      ) : null}

      {phase === 'active' && activeQuestion ? (
        <>
          <Card className='span-12' style={{ position: 'sticky', top: 8, zIndex: 3 }}>
            <div className='row' style={{ justifyContent: 'space-between', gap: 12 }}>
              <strong>Tiến độ: Câu {currentQuestionIndex + 1}/{questions.length}</strong>
              <Badge tone={getTimerTone(timeLeft)}>{formatTime(timeLeft)}</Badge>
            </div>
          </Card>

          <Card className='span-12 stack-md'>
            <div className='row' style={{ gap: 8, flexWrap: 'wrap' }}>
              <Badge tone={DIFFICULTY_TONE[activeQuestion.difficulty] || 'warning'}>
                {DIFFICULTY_LABEL[activeQuestion.difficulty] || activeQuestion.difficulty}
              </Badge>
              <Badge tone='info'>{activeQuestion.topic || 'Chung'}</Badge>
            </div>

            <p style={{ margin: 0, fontWeight: 600 }}>{activeQuestion.stem}</p>

            {activeQuestion.type === 'essay' ? (
              <div className='stack-sm'>
                <textarea
                  rows={6}
                  value={typeof answers[activeQuestion.id] === 'string' ? answers[activeQuestion.id] : ''}
                  onChange={(e) => handleEssayChange(activeQuestion.id, e.target.value)}
                  placeholder='Nhập câu trả lời tự luận...'
                />
                <small>
                  Word count: {String(answers[activeQuestion.id] || '').trim().split(/\s+/).filter(Boolean).length}
                </small>
              </div>
            ) : (
              <div className='stack-sm'>
                {(activeQuestion.options || []).map((option, index) => (
                  <label
                    key={`${activeQuestion.id}-${index}`}
                    style={{
                      display: 'block',
                      padding: 10,
                      borderRadius: 8,
                      border: answers[activeQuestion.id] === index ? '1px solid #2563eb' : '1px solid #e2e8f0',
                      background: answers[activeQuestion.id] === index ? '#eff6ff' : '#fff',
                    }}
                  >
                    <input
                      type='radio'
                      name={`question-${activeQuestion.id}`}
                      checked={answers[activeQuestion.id] === index}
                      onChange={() => handleSelectMcq(activeQuestion.id, index)}
                    />{' '}
                    <strong>{OPTION_LABELS[index] || `${index + 1}`}. </strong>
                    <span>{option}</span>
                  </label>
                ))}
              </div>
            )}

            <div className='row' style={{ justifyContent: 'space-between', alignItems: 'center' }}>
              <div className='row' style={{ gap: 8 }}>
                {questions.map((q, idx) => (
                  <button
                    type='button'
                    key={q.id}
                    onClick={() => setCurrentQuestionIndex(idx)}
                    aria-label={`Đi tới câu ${idx + 1}`}
                    style={{
                      width: 12,
                      height: 12,
                      borderRadius: '50%',
                      border: 'none',
                      background: idx === currentQuestionIndex ? '#2563eb' : isAnswered(q, answers[q.id]) ? '#22c55e' : '#cbd5e1',
                      cursor: 'pointer',
                    }}
                  />
                ))}
              </div>

              <div className='row' style={{ gap: 8 }}>
                <Button
                  onClick={() => setCurrentQuestionIndex((prev) => Math.max(0, prev - 1))}
                  disabled={currentQuestionIndex === 0}
                >
                  Prev
                </Button>
                <Button
                  onClick={() => setCurrentQuestionIndex((prev) => Math.min(questions.length - 1, prev + 1))}
                  disabled={currentQuestionIndex >= questions.length - 1}
                >
                  Next
                </Button>
              </div>
            </div>
          </Card>

          <Card className='span-12' style={{ position: 'sticky', bottom: 8, zIndex: 3 }}>
            <div className='row' style={{ justifyContent: 'space-between', alignItems: 'center' }}>
              <strong>Đã trả lời {answeredCount}/{questions.length}</strong>
              <Button variant='primary' onClick={() => setConfirmOpen(true)}>Nộp bài</Button>
            </div>
          </Card>
        </>
      ) : null}

      {phase === 'result' && result ? (
        <Card className='span-12 stack-md'>
          <div
            style={{
              padding: 16,
              borderRadius: 12,
              border: '1px solid #e2e8f0',
              background: '#f8fafc',
            }}
          >
            <h2 style={{ margin: 0 }}>
              {Math.round(Number(result.score) || 0)}/100 – Phân loại: {CLASSIFICATION_LABEL[classification] || classification}
            </h2>
            <div style={{ marginTop: 12, height: 10, background: '#e2e8f0', borderRadius: 999 }}>
              <div
                style={{
                  width: `${Math.max(0, Math.min(100, percentage))}%`,
                  height: '100%',
                  borderRadius: 999,
                  background: CLASSIFICATION_COLOR[classification] || '#3b82f6',
                }}
              />
            </div>
          </div>

          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th align='left'>Độ khó</th>
                <th align='left'>Đúng</th>
                <th align='left'>Sai</th>
                <th align='left'>Điểm</th>
              </tr>
            </thead>
            <tbody>
              {['easy', 'medium', 'hard'].map((key) => {
                const row = result?.breakdown_by_difficulty?.[key] || { correct: 0, total: 0 }
                const total = Number(row.total) || 0
                const correct = Number(row.correct) || 0
                const wrong = Math.max(0, total - correct)
                const pct = total > 0 ? Math.round((correct / total) * 100) : 0

                return (
                  <tr key={key}>
                    <td>{DIFFICULTY_LABEL[key]}</td>
                    <td>{correct}/{total}</td>
                    <td>{wrong}</td>
                    <td>{pct}%</td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          <div className='stack-sm'>
            <Button onClick={() => setTopicExpanded((prev) => !prev)}>
              {topicExpanded ? 'Ẩn breakdown theo topic' : 'Xem breakdown theo topic'}
            </Button>
            {topicExpanded ? (
              <div className='stack-sm'>
                {(result.breakdown_by_topic || []).map((row) => (
                  <div key={row.topic} className='row' style={{ justifyContent: 'space-between' }}>
                    <span>{row.topic}</span>
                    <span>{row.correct}/{row.total} ({Math.round(row.percentage || 0)}%)</span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          <div
            style={{
              background: '#f5f3ff',
              border: '1px solid #ddd6fe',
              borderRadius: 10,
              padding: 12,
            }}
          >
            <strong>AI recommendation</strong>
            <p style={{ marginBottom: 0 }}>{result.ai_recommendation || 'Chưa có gợi ý.'}</p>
          </div>

          <div className='row' style={{ gap: 8 }}>
            <Button variant='primary' onClick={() => navigate('/learning-path')}>Xem lộ trình học</Button>
            <Button onClick={loadQuizSet}>Làm lại bài kiểm tra</Button>
          </div>
        </Card>
      ) : null}

      <Modal
        open={confirmOpen}
        title='Xác nhận nộp bài'
        onClose={() => setConfirmOpen(false)}
        actions={(
          <>
            <Button onClick={() => setOpenConfirm(false)}>Huỷ</Button>
            <Button variant='primary' onClick={() => handleSubmit(false)} disabled={submitting || !allAnswered}>Xác nhận nộp</Button>
          </>
        )}
      >
        Xác nhận nộp bài ngay?
            <Button onClick={() => setConfirmOpen(false)}>Hủy</Button>
            <Button variant='primary' onClick={() => handleSubmit(false)}>Xác nhận nộp</Button>
          </>
        )}
      >
        Bạn đã trả lời {answeredCount}/{questions.length} câu. Bạn có chắc muốn nộp bài?
      </Modal>
    </div>
  )
}
