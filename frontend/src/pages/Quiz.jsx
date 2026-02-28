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

      <Modal
        open={openConfirm}
        title='Xác nhận nộp bài'
        onClose={() => setOpenConfirm(false)}
        actions={(
          <>
            <Button onClick={() => setOpenConfirm(false)}>Huỷ</Button>
            <Button variant='primary' onClick={() => handleSubmit(false)} disabled={submitting || !allAnswered}>Xác nhận nộp</Button>
          </>
        )}
      >
        Xác nhận nộp bài ngay?
      </Modal>
    </div>
  );
}
