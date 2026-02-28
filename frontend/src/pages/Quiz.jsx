import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Modal from '../ui/Modal';
import Banner from '../ui/Banner';
import PageHeader from '../ui/PageHeader';
import { apiJson } from '../lib/api';

function normalizeOption(option, index) {
  if (typeof option === 'string') {
    return { value: index, label: option };
  }

  return {
    value: option?.id ?? option?.value ?? option?.key ?? index,
    label: option?.label ?? option?.text ?? option?.content ?? `Lựa chọn ${index + 1}`,
  };
}

function normalizeQuestion(question, index) {
  return {
    question_id: String(question?.question_id ?? question?.id ?? `q_${index}`),
    topic: question?.topic || question?.topic_name || 'Chung',
    stem: question?.stem || question?.question_text || question?.content || `Câu hỏi ${index + 1}`,
    options: (Array.isArray(question?.options) ? question.options : []).map(normalizeOption),
  };
}

function formatMMSS(totalSec = 0) {
  const sec = Math.max(0, Number(totalSec) || 0);
  const mm = String(Math.floor(sec / 60)).padStart(2, '0');
  const ss = String(sec % 60).padStart(2, '0');
  return `${mm}:${ss}`;
}

function renderTopicBreakdown(topicMap) {
  if (!topicMap || typeof topicMap !== 'object') return [];

  return Object.entries(topicMap).map(([topic, item]) => {
    if (typeof item === 'number') {
      return { topic, correct: item, total: item };
    }

    return {
      topic,
      correct: item?.correct ?? item?.score ?? item?.correct_count ?? 0,
      total: item?.total ?? item?.total_questions ?? item?.max_score ?? 0,
    };
  });
}

export default function Quiz() {
  const { quizSetId } = useParams();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [openConfirm, setOpenConfirm] = useState(false);

  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [timeLeftSec, setTimeLeftSec] = useState(0);
  const [submitted, setSubmitted] = useState(false);
  const [result, setResult] = useState(null);

  const autoSubmitRef = useRef(false);

  const answeredCount = useMemo(
    () => Object.values(answers).filter((value) => value !== undefined && value !== null).length,
    [answers],
  );
  const allAnswered = questions.length > 0 && answeredCount === questions.length;
  const isTimeUp = timeLeftSec <= 0;
  const canSubmit = allAnswered || isTimeUp;

  const loadQuiz = useCallback(async () => {
    if (!quizSetId) {
      setError('Không tìm thấy quizSetId trên URL.');
      setLoading(false);
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await apiJson(`/v1/assessments/${encodeURIComponent(quizSetId)}/questions`);
      const normalizedQuestions = (Array.isArray(response?.questions) ? response.questions : []).map(normalizeQuestion);

      if (!normalizedQuestions.length) {
        throw new Error('Bộ đề chưa có câu hỏi.');
      }

      const durationSec = Number(response?.duration_seconds);
      if (!Number.isFinite(durationSec) || durationSec <= 0) {
        throw new Error('duration_seconds không hợp lệ từ API.');
      }

      setQuestions(normalizedQuestions);
      setAnswers({});
      setTimeLeftSec(Math.floor(durationSec));
      setSubmitted(false);
      setResult(null);
      autoSubmitRef.current = false;
    } catch (loadError) {
      setError(loadError?.message || 'Không thể tải bộ câu hỏi.');
    } finally {
      setLoading(false);
    }
  }, [quizSetId]);

  const handleSubmit = useCallback(
    async (autoSubmit = false) => {
      if (!quizSetId || submitted || submitting) return;

      if (!autoSubmit && !canSubmit) {
        setError('Bạn cần trả lời đủ câu hỏi trước khi nộp bài.');
        return;
      }

      setSubmitting(true);
      setError('');

      try {
        const payload = {
          answers: questions.reduce((acc, question) => {
            acc[question.question_id] = answers[question.question_id] ?? null;
            return acc;
          }, {}),
        };

        const response = await apiJson(`/v1/assessments/${encodeURIComponent(quizSetId)}/submit`, {
          method: 'POST',
          body: payload,
        });

        setResult({
          ...response,
          autoSubmitted: autoSubmit,
          breakdownRows: renderTopicBreakdown(response?.breakdown_by_topic),
        });
        setSubmitted(true);
      } catch (submitError) {
        setError(submitError?.message || 'Nộp bài thất bại.');
      } finally {
        setSubmitting(false);
        setOpenConfirm(false);
      }
    },
    [answers, canSubmit, questions, quizSetId, submitted, submitting],
  );

  useEffect(() => {
    loadQuiz();
  }, [loadQuiz]);

  useEffect(() => {
    if (loading || submitted || !questions.length) return undefined;

    const intervalId = setInterval(() => {
      setTimeLeftSec((prev) => {
        if (prev <= 1) {
          if (!autoSubmitRef.current) {
            autoSubmitRef.current = true;
            setTimeout(() => handleSubmit(true), 0);
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(intervalId);
  }, [handleSubmit, loading, questions.length, submitted]);

  const dangerTime = timeLeftSec < 60;

  return (
    <div className='container grid-12'>
      <Card className='span-12'>
        <PageHeader
          title='Placement Quiz / Diagnostic Pre'
          subtitle='Làm bài kiểm tra đầu vào để hệ thống đánh giá năng lực ban đầu.'
          breadcrumbs={['Học sinh', 'Diagnostic Pre']}
          right={<Banner tone={dangerTime ? 'danger' : 'info'}>⏱ {formatMMSS(timeLeftSec)}</Banner>}
        />
      </Card>

      {loading ? (
        <Card className='span-12'>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 18, height: 18, border: '2px solid #cbd5e1', borderTopColor: '#2563eb', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
            <span>Đang tải bài kiểm tra từ hệ thống...</span>
          </div>
        </Card>
      ) : null}

      {!loading && error ? (
        <Card className='span-12 stack-sm'>
          <Banner tone='danger'>{error}</Banner>
          {!submitted ? <Button onClick={loadQuiz} disabled={submitting}>Tải lại</Button> : null}
        </Card>
      ) : null}

      {!loading && !error && questions.length > 0 ? (
        <Card className='span-12 stack-md'>
          <Banner tone={allAnswered ? 'success' : 'warning'}>
            Đã trả lời {answeredCount}/{questions.length} câu
            {!allAnswered ? ` · Còn ${questions.length - answeredCount} câu chưa trả lời` : ' · Bạn đã trả lời đầy đủ'}
          </Banner>

          {questions.map((question, index) => {
            const selectedValue = answers[question.question_id];

            return (
              <div key={question.question_id} className='ui-card stack-sm'>
                <div className='row'>
                  <strong>Câu {index + 1}</strong>
                  <span style={{ fontSize: 12, fontWeight: 600 }}>{question.topic}</span>
                </div>

                <p style={{ margin: 0 }}>{question.stem}</p>

                <div className='stack-sm'>
                  {question.options.map((option) => (
                    <label
                      key={`${question.question_id}-${option.value}`}
                      style={{
                        padding: 10,
                        borderRadius: 8,
                        border: selectedValue === option.value ? '1px solid #2563eb' : '1px solid #e2e8f0',
                        background: selectedValue === option.value ? '#eff6ff' : '#fff',
                        opacity: submitted ? 0.7 : 1,
                      }}
                    >
                      <input
                        type='radio'
                        name={`question-${question.question_id}`}
                        checked={selectedValue === option.value}
                        disabled={submitted || submitting}
                        onChange={() => setAnswers((prev) => ({ ...prev, [question.question_id]: option.value }))}
                      />{' '}
                      {option.label}
                    </label>
                  ))}
                </div>
              </div>
            );
          })}

          <div className='row'>
            <Button variant='primary' onClick={() => setOpenConfirm(true)} disabled={submitting || submitted || !canSubmit}>
              {submitting ? 'Đang nộp...' : submitted ? 'Đã nộp' : 'Nộp bài'}
            </Button>
          </div>
        </Card>
      ) : null}

      {result ? (
        <Card className='span-12 stack-sm'>
          <Banner tone='success'>
            Kết quả: {result.score ?? 0} · Xếp loại: {result.classification ?? 'N/A'}
            {result.autoSubmitted ? ' · Tự động nộp do hết giờ' : ''}
          </Banner>

          <div className='stack-sm'>
            <strong>Breakdown theo chủ đề</strong>
            {result.breakdownRows?.length ? (
              result.breakdownRows.map((row) => (
                <div key={row.topic} className='row'>
                  <span>{row.topic}</span>
                  <span>{row.correct}/{row.total}</span>
                </div>
              ))
            ) : (
              <span>Chưa có dữ liệu breakdown_by_topic.</span>
            )}
          </div>
        </Card>
      ) : null}

      <Modal
        open={openConfirm}
        title='Xác nhận nộp bài'
        onClose={() => setOpenConfirm(false)}
        actions={(
          <>
            <Button onClick={() => setOpenConfirm(false)}>Huỷ</Button>
            <Button variant='primary' onClick={() => handleSubmit(false)} disabled={submitting || !canSubmit}>
              {submitting ? 'Đang nộp...' : 'Xác nhận nộp'}
            </Button>
          </>
        )}
      >
        {!allAnswered && !isTimeUp
          ? `Bạn còn ${questions.length - answeredCount} câu chưa trả lời. Chỉ có thể nộp khi trả lời đủ hoặc hết giờ.`
          : 'Xác nhận nộp bài ngay?'}
      </Modal>
    </div>
  );
}
