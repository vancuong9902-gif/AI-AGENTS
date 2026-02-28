import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Modal from '../ui/Modal';
import Banner from '../ui/Banner';
import PageHeader from '../ui/PageHeader';
import { apiJson } from '../lib/api';
import { useAuth } from '../context/AuthContext';

const difficultyLabel = {
  easy: 'Dễ',
  medium: 'Trung bình',
  hard: 'Khó',
};

const difficultyTone = {
  easy: { color: '#166534', background: '#dcfce7' },
  medium: { color: '#1d4ed8', background: '#dbeafe' },
  hard: { color: '#991b1b', background: '#fee2e2' },
};

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
  const difficulty = String(question?.difficulty || 'medium').toLowerCase();

  return {
    question_id: question?.question_id ?? question?.id ?? `q_${index}`,
    topic: question?.topic || question?.topic_name || 'Chung',
    difficulty: difficultyLabel[difficulty] ? difficulty : 'medium',
    stem: question?.stem || question?.question_text || question?.content || `Câu hỏi ${index + 1}`,
    options: (Array.isArray(question?.options) ? question.options : []).slice(0, 4).map(normalizeOption),
  };
}

function parseTopicIds(searchParams, topicIdFromPath) {
  const ids = [];

  const rawList = searchParams.getAll('topic_ids');
  rawList.forEach((raw) => {
    raw
      .split(',')
      .map((v) => Number(v.trim()))
      .filter(Number.isFinite)
      .forEach((v) => ids.push(v));
  });

  const topicFromPath = Number(topicIdFromPath);
  if (Number.isFinite(topicFromPath)) ids.push(topicFromPath);

  return [...new Set(ids)];
}

function toSeconds(minutes) {
  const safeMinutes = Number(minutes);
  if (!Number.isFinite(safeMinutes) || safeMinutes <= 0) return 0;
  return Math.round(safeMinutes * 60);
}

function formatMMSS(totalSec = 0) {
  const sec = Math.max(0, totalSec);
  const mm = String(Math.floor(sec / 60)).padStart(2, '0');
  const ss = String(sec % 60).padStart(2, '0');
  return `${mm}:${ss}`;
}

export default function Quiz() {
  const navigate = useNavigate();
  const { userId } = useAuth();
  const { topicId, assessmentId: assessmentIdFromPath } = useParams();
  const [searchParams] = useSearchParams();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [openConfirm, setOpenConfirm] = useState(false);

  const [quizMeta, setQuizMeta] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [timeLeftSec, setTimeLeftSec] = useState(0);

  const autoSubmitRef = useRef(false);
  const submitRef = useRef(null);

  const resolvedAssessmentId =
    searchParams.get('assessmentId') ||
    searchParams.get('assessment_id') ||
    assessmentIdFromPath ||
    null;
  const documentId =
    searchParams.get('document_id') ||
    searchParams.get('docId') ||
    localStorage.getItem('document_id') ||
    null;
  const topicIds = parseTopicIds(searchParams, topicId);

  const answeredCount = useMemo(() => Object.values(answers).filter((value) => value !== undefined && value !== null).length, [answers]);
  const unansweredCount = Math.max(0, questions.length - answeredCount);

  const loadQuiz = useCallback(async () => {
    setLoading(true);
    setError('');

    try {
      let assessment = null;

      if (resolvedAssessmentId) {
        assessment = await apiJson(`/assessments/${resolvedAssessmentId}`);
      } else {
        const diagnostic = await apiJson(
          `/lms/diagnostic/pre?user_id=${encodeURIComponent(userId)}&document_id=${encodeURIComponent(documentId || '')}`,
        );

        const hasQuestions = Array.isArray(diagnostic?.questions) && diagnostic.questions.length > 0;
        const diagnosticAssessmentId = diagnostic?.assessment_id || diagnostic?.quiz_id || diagnostic?.id;

        if (hasQuestions) {
          assessment = diagnostic;
        } else if (diagnosticAssessmentId) {
          assessment = await apiJson(`/assessments/${diagnosticAssessmentId}`);
        } else {
          const generated = await apiJson('/lms/entry-test/generate', {
            method: 'POST',
            body: {
              user_id: userId,
              document_id: documentId ? Number(documentId) || documentId : null,
              topic_ids: topicIds,
            },
          });

          const generatedAssessmentId = generated?.assessment_id || generated?.quiz_id || generated?.id;
          if (Array.isArray(generated?.questions) && generated.questions.length > 0) {
            assessment = generated;
          } else if (generatedAssessmentId) {
            assessment = await apiJson(`/assessments/${generatedAssessmentId}`);
          }
        }
      }

      if (!assessment) {
        throw new Error('Không tìm thấy bài kiểm tra đầu vào phù hợp.');
      }

      const normalizedQuestions = (Array.isArray(assessment?.questions) ? assessment.questions : []).map(normalizeQuestion);
      if (!normalizedQuestions.length) {
        throw new Error('Bài kiểm tra chưa có câu hỏi.');
      }

      const limitSec = toSeconds(assessment?.time_limit_minutes);
      if (limitSec <= 0) {
        throw new Error('Bài kiểm tra chưa có thời lượng hợp lệ từ API.');
      }

      setQuizMeta({
        assessmentId: assessment?.assessment_id || assessment?.quiz_id || assessment?.id,
        timeLimitMinutes: assessment?.time_limit_minutes,
      });
      setQuestions(normalizedQuestions);
      setAnswers({});
      setTimeLeftSec(limitSec);
      autoSubmitRef.current = false;
    } catch (loadError) {
      setError(loadError?.message || 'Không thể tải bài kiểm tra.');
    } finally {
      setLoading(false);
    }
  }, [documentId, resolvedAssessmentId, topicIds, userId]);

  const handleSubmit = useCallback(
    async (autoSubmit = false) => {
      if (submitting || !quizMeta?.assessmentId) return;

      setSubmitting(true);
      setError('');

      try {
        const payload = {
          user_id: userId,
          answers: questions.map((question) => ({
            question_id: question.question_id,
            selected_option: answers[question.question_id] ?? null,
          })),
          auto_submitted: autoSubmit,
        };

        const response = await apiJson(`/assessments/${quizMeta.assessmentId}/submit`, {
          method: 'POST',
          body: payload,
        });

        navigate('/result', {
          state: {
            quizResult: response,
            quizType: 'diagnostic_pre',
          },
        });
      } catch (submitError) {
        setError(submitError?.message || 'Nộp bài thất bại.');
      } finally {
        setSubmitting(false);
        setOpenConfirm(false);
      }
    },
    [answers, navigate, questions, quizMeta?.assessmentId, submitting, userId],
  );

  submitRef.current = handleSubmit;

  useEffect(() => {
    loadQuiz();
  }, [loadQuiz]);

  useEffect(() => {
    if (loading || submitting || !questions.length || timeLeftSec <= 0) return undefined;

    const intervalId = setInterval(() => {
      setTimeLeftSec((prev) => {
        if (prev <= 1) {
          clearInterval(intervalId);
          if (!autoSubmitRef.current) {
            autoSubmitRef.current = true;
            submitRef.current?.(true);
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(intervalId);
  }, [loading, questions.length, submitting, timeLeftSec]);

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
          <Button onClick={loadQuiz} disabled={submitting}>Tải lại</Button>
        </Card>
      ) : null}

      {!loading && !error && questions.length > 0 ? (
        <Card className='span-12 stack-md'>
          <Banner tone={unansweredCount ? 'warning' : 'success'}>
            Câu {answeredCount}/{questions.length} đã trả lời
            {unansweredCount > 0 ? ` · Bạn còn ${unansweredCount} câu chưa trả lời` : ' · Bạn đã trả lời đầy đủ'}
          </Banner>

          {questions.map((question, index) => {
            const badgeStyle = difficultyTone[question.difficulty] || difficultyTone.medium;
            const selectedValue = answers[question.question_id];

            return (
              <div key={question.question_id} className='ui-card stack-sm'>
                <div className='row'>
                  <strong>Câu {index + 1}</strong>
                  <span
                    style={{
                      background: badgeStyle.background,
                      color: badgeStyle.color,
                      borderRadius: 999,
                      padding: '4px 10px',
                      fontSize: 12,
                      fontWeight: 600,
                    }}
                  >
                    {difficultyLabel[question.difficulty]} · {question.topic}
                  </span>
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
                      }}
                    >
                      <input
                        type='radio'
                        name={`question-${question.question_id}`}
                        checked={selectedValue === option.value}
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
            <Button variant='primary' onClick={() => setOpenConfirm(true)} disabled={submitting}>
              {submitting ? 'Đang nộp...' : 'Nộp bài'}
            </Button>
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
            <Button variant='primary' onClick={() => handleSubmit(false)} disabled={submitting}>
              {submitting ? 'Đang nộp...' : 'Xác nhận nộp'}
            </Button>
          </>
        )}
      >
        {unansweredCount > 0 ? `Bạn còn ${unansweredCount} câu chưa trả lời. Bạn vẫn muốn nộp bài?` : 'Bạn đã trả lời đầy đủ. Xác nhận nộp bài ngay?'}
      </Modal>
    </div>
  );
}
