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
