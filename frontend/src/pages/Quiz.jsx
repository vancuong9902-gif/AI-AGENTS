import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { apiJson } from '../lib/api';
import Banner from '../ui/Banner';
import Button from '../ui/Button';
import Card from '../ui/Card';
import Modal from '../ui/Modal';
import PageHeader from '../ui/PageHeader';

const DEFAULT_DIFFICULTY_SETTINGS = { easy: 4, medium: 4, hard: 2 };
const DEFAULT_DURATION_SECONDS = 1800;

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function toNumber(value, fallback = null) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function resolveQuestionType(question) {
  const rawType = String(question?.type || question?.question_type || '').toLowerCase();
  if (rawType.includes('essay') || rawType.includes('text')) return 'essay';
  return 'mcq';
}

function normalizeQuestion(question, index) {
  const questionId = toNumber(question?.question_id ?? question?.id, index + 1);
  const type = resolveQuestionType(question);
  const options = asArray(question?.options).map((option, optionIndex) => {
    if (typeof option === 'string') return option;
    return option?.label ?? option?.text ?? option?.content ?? `Lựa chọn ${optionIndex + 1}`;
  });

  return {
    id: questionId,
    type,
    stem: question?.stem ?? question?.question_text ?? question?.content ?? `Câu hỏi ${index + 1}`,
    options,
  };
}

function formatClock(totalSeconds) {
  const safe = Math.max(0, toNumber(totalSeconds, 0));
  const mm = Math.floor(safe / 60)
    .toString()
    .padStart(2, '0');
  const ss = Math.floor(safe % 60)
    .toString()
    .padStart(2, '0');
  return `${mm}:${ss}`;
}

export default function Quiz() {
  const { topicId } = useParams();
  const navigate = useNavigate();
  const { userId } = useAuth();

  const [bootLoading, setBootLoading] = useState(true);
  const [bootError, setBootError] = useState('');
  const [classroom, setClassroom] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState(null);
  const [topics, setTopics] = useState([]);
  const [selectedTopicIds, setSelectedTopicIds] = useState([]);

  const [starting, setStarting] = useState(false);
  const [attemptId, setAttemptId] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [timeLeftSec, setTimeLeftSec] = useState(0);
  const [submitError, setSubmitError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const timerRef = useRef(null);
  const submittedRef = useRef(false);

  const activeClassroomId = toNumber(localStorage.getItem('active_classroom_id'), 0);

  const quizActive = questions.length > 0 && !!attemptId;
  const answeredCount = useMemo(
    () => questions.reduce((acc, question) => {
      const value = answers[question.id];
      if (question.type === 'essay') return acc + (typeof value === 'string' && value.trim().length > 0 ? 1 : 0);
      return acc + (typeof value === 'number' ? 1 : 0);
    }, 0),
    [answers, questions],
  );

  const loadBootData = useCallback(async () => {
    setBootLoading(true);
    setBootError('');

    if (!activeClassroomId) {
      setBootLoading(false);
      return;
    }

    try {
      const classroomsResponse = await apiJson('/classrooms');
      const classrooms = asArray(classroomsResponse);
      const activeClassroom = classrooms.find((item) => toNumber(item?.id, -1) === activeClassroomId);

      if (!activeClassroom) throw new Error('Không tìm thấy lớp học đang hoạt động.');
      setClassroom(activeClassroom);

      const docsResponse = await apiJson('/documents');
      const docs = asArray(docsResponse);
      setDocuments(docs);

      if (!docs.length) {
        setSelectedDocumentId(null);
        return;
      }

      const persistedDocId = toNumber(localStorage.getItem('active_document_id'), null);
      const docToUse = docs.find((doc) => toNumber(doc?.id, -1) === persistedDocId)
        || docs.reduce((latest, current) => {
          const latestTime = new Date(latest?.created_at || 0).getTime() || 0;
          const currentTime = new Date(current?.created_at || 0).getTime() || 0;
          if (currentTime === latestTime) {
            return toNumber(current?.id, 0) > toNumber(latest?.id, 0) ? current : latest;
          }
          return currentTime > latestTime ? current : latest;
        }, docs[0]);

      const resolvedDocId = toNumber(docToUse?.id, null);
      setSelectedDocumentId(resolvedDocId);
      if (resolvedDocId) {
        localStorage.setItem('active_document_id', String(resolvedDocId));
      }
    } catch (error) {
      setBootError(error?.message || 'Không thể tải dữ liệu khởi tạo Placement Test.');
    } finally {
      setBootLoading(false);
    }
  }, [activeClassroomId]);

  const loadTopics = useCallback(async (documentId) => {
    if (!documentId) {
      setTopics([]);
      setSelectedTopicIds([]);
      return;
    }

    try {
      const topicsResponse = await apiJson(`/documents/${encodeURIComponent(documentId)}/topics`);
      const topicRows = asArray(topicsResponse);
      setTopics(topicRows);

      const persisted = (() => {
        try {
          const parsed = JSON.parse(localStorage.getItem('selected_topic_ids') || '[]');
          return asArray(parsed).map((id) => toNumber(id, null)).filter((id) => id != null);
        } catch {
          return [];
        }
      })();

      const availableIds = new Set(topicRows.map((item) => toNumber(item?.id, -1)));
      const fromStorage = persisted.filter((id) => availableIds.has(id));
      const preselectedTopicFromRoute = toNumber(topicId, null);

      let nextSelected = fromStorage;
      if (!nextSelected.length && preselectedTopicFromRoute && availableIds.has(preselectedTopicFromRoute)) {
        nextSelected = [preselectedTopicFromRoute];
      }

      setSelectedTopicIds(nextSelected);
      localStorage.setItem('selected_topic_ids', JSON.stringify(nextSelected));
    } catch (error) {
      setTopics([]);
      setSelectedTopicIds([]);
      setBootError(error?.message || 'Không thể tải danh sách topic.');
    }
  }, [topicId]);

  useEffect(() => {
    loadBootData();
  }, [loadBootData]);

  useEffect(() => {
    if (selectedDocumentId) {
      localStorage.setItem('active_document_id', String(selectedDocumentId));
      loadTopics(selectedDocumentId);
    }
  }, [loadTopics, selectedDocumentId]);

  useEffect(() => {
    localStorage.setItem('selected_topic_ids', JSON.stringify(selectedTopicIds));
  }, [selectedTopicIds]);

  useEffect(() => {
    if (!quizActive) return undefined;

    timerRef.current = setInterval(() => {
      setTimeLeftSec((prev) => {
        if (prev <= 1) {
          clearInterval(timerRef.current);
          timerRef.current = null;
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [quizActive]);

  const submitAttempt = useCallback(async (auto = false) => {
    if (!attemptId || submitting || submittedRef.current) return;

    submittedRef.current = true;
    setSubmitting(true);
    setSubmitError('');

    try {
      const payload = {
        answers: questions.map((question) => ({
          question_id: question.id,
          answer_index: question.type === 'mcq' ? (typeof answers[question.id] === 'number' ? answers[question.id] : null) : null,
          answer_text: question.type === 'essay'
            ? (typeof answers[question.id] === 'string' && answers[question.id].trim().length > 0 ? answers[question.id].trim() : null)
            : null,
        })),
      };

      const response = await apiJson(`/attempts/${encodeURIComponent(attemptId)}/submit`, {
        method: 'POST',
        body: payload,
      });

      navigate('/result', {
        state: { type: 'entry', result: response, autoSubmitted: auto },
      });
    } catch (error) {
      submittedRef.current = false;
      setSubmitError(error?.message || 'Nộp bài thất bại.');
    } finally {
      setSubmitting(false);
      setConfirmOpen(false);
    }
  }, [answers, attemptId, navigate, questions, submitting]);

  useEffect(() => {
    if (!quizActive || timeLeftSec > 0) return;
    submitAttempt(true);
  }, [quizActive, submitAttempt, timeLeftSec]);

  const handleToggleTopic = (id) => {
    setSelectedTopicIds((prev) => {
      if (prev.includes(id)) return prev.filter((item) => item !== id);
      return [...prev, id];
    });
  };

  const handleStart = async () => {
    if (!classroom || !selectedTopicIds.length || starting) return;

    setStarting(true);
    setSubmitError('');
    submittedRef.current = false;

    try {
      const storedMinutes = toNumber(localStorage.getItem('time_limit_minutes'), null);
      const durationSeconds = storedMinutes && storedMinutes > 0 ? storedMinutes * 60 : DEFAULT_DURATION_SECONDS;

      const placement = await apiJson('/quizzes/placement', {
        method: 'POST',
        body: {
          topic_ids: selectedTopicIds,
          difficulty_settings: DEFAULT_DIFFICULTY_SETTINGS,
          duration_seconds: durationSeconds,
          teacher_id: toNumber(classroom?.teacher_id ?? classroom?.teacherId, 0),
          classroom_id: activeClassroomId,
        },
      });

      const assessmentId = toNumber(
        placement?.assessment_id ?? placement?.quiz_id ?? placement?.id,
        null,
      );
      if (!assessmentId) throw new Error('Backend chưa trả về assessment_id hợp lệ.');

      const startResp = await apiJson('/attempts/start', {
        method: 'POST',
        body: {
          quiz_id: assessmentId,
          student_id: toNumber(userId, 0),
        },
      });

      const normalizedQuestions = asArray(placement?.questions).map(normalizeQuestion);
      if (!normalizedQuestions.length) throw new Error('Quiz không có câu hỏi để hiển thị.');

      setQuestions(normalizedQuestions);
      setAnswers({});
      setAttemptId(toNumber(startResp?.attempt_id ?? startResp?.id, null));

      const apiDurationSec = toNumber(placement?.duration_seconds, null);
      const apiMinutes = toNumber(placement?.time_limit_minutes, null);
      const resolvedTime = apiDurationSec ?? (apiMinutes && apiMinutes > 0 ? apiMinutes * 60 : durationSeconds);
      setTimeLeftSec(resolvedTime || DEFAULT_DURATION_SECONDS);
    } catch (error) {
      setSubmitError(error?.message || 'Không thể bắt đầu Placement Test.');
    } finally {
      setStarting(false);
    }
  };

  return (
    <div className='container grid-12'>
      <Card className='span-12'>
        <PageHeader
          title='Placement Test'
          subtitle='Làm bài kiểm tra đầu vào theo topic tài liệu để hệ thống phân loại năng lực.'
          breadcrumbs={['Học sinh', 'Placement Test']}
        />
      </Card>

      {!activeClassroomId ? (
        <Card className='span-12 stack-sm'>
          <Banner tone='warning'>Bạn chưa chọn lớp học đang hoạt động.</Banner>
          <Button onClick={() => navigate('/classrooms')} variant='primary'>Đi đến trang lớp học</Button>
        </Card>
      ) : null}

      {activeClassroomId && bootLoading ? (
        <Card className='span-12'>
          <Banner tone='info'>Đang tải lớp học, tài liệu và topic...</Banner>
        </Card>
      ) : null}

      {activeClassroomId && !bootLoading && bootError ? (
        <Card className='span-12'>
          <Banner tone='error'>{bootError}</Banner>
        </Card>
      ) : null}

      {activeClassroomId && !bootLoading && !bootError && !quizActive ? (
        <Card className='span-12 stack-md'>
          <div>
            <strong>Tài liệu</strong>
            <div className='row' style={{ marginTop: 8, gap: 8, flexWrap: 'wrap' }}>
              {documents.map((doc) => {
                const docId = toNumber(doc?.id, 0);
                return (
                  <Button
                    key={docId}
                    variant={docId === selectedDocumentId ? 'primary' : 'ghost'}
                    onClick={() => setSelectedDocumentId(docId)}
                  >
                    {doc?.title || doc?.name || `Document #${docId}`}
                  </Button>
                );
              })}
            </div>
          </div>

          <div>
            <strong>Chọn topic</strong>
            {!topics.length ? (
              <Banner tone='warning'>Tài liệu chưa có topic để tạo Placement Test.</Banner>
            ) : (
              <div className='stack-sm' style={{ marginTop: 8 }}>
                {topics.map((topic) => {
                  const id = toNumber(topic?.id, 0);
                  return (
                    <label key={id}>
                      <input
                        type='checkbox'
                        checked={selectedTopicIds.includes(id)}
                        onChange={() => handleToggleTopic(id)}
                      />{' '}
                      {topic?.title || topic?.name || `Topic #${id}`}
                    </label>
                  );
                })}
              </div>
            )}
          </div>

          {submitError ? <Banner tone='error'>{submitError}</Banner> : null}

          <Button variant='primary' onClick={handleStart} disabled={!selectedTopicIds.length || starting || !topics.length}>
            {starting ? 'Đang tạo bài...' : 'Bắt đầu'}
          </Button>
        </Card>
      ) : null}

      {quizActive ? (
        <Card className='span-12 stack-md'>
          <Banner tone={timeLeftSec <= 60 ? 'error' : timeLeftSec <= 300 ? 'warning' : 'info'}>
            ⏱ {formatClock(timeLeftSec)} · Đã trả lời {answeredCount}/{questions.length}
          </Banner>

          {questions.map((question, index) => (
            <div key={question.id} className='ui-card stack-sm'>
              <strong>Câu {index + 1}</strong>
              <p style={{ margin: 0 }}>{question.stem}</p>

              {question.type === 'essay' ? (
                <textarea
                  rows={5}
                  value={typeof answers[question.id] === 'string' ? answers[question.id] : ''}
                  onChange={(event) => setAnswers((prev) => ({ ...prev, [question.id]: event.target.value }))}
                  disabled={submitting}
                  placeholder='Nhập câu trả lời tự luận...'
                />
              ) : (
                <div className='stack-sm'>
                  {question.options.map((option, optionIndex) => (
                    <label key={`${question.id}-${optionIndex}`}>
                      <input
                        type='radio'
                        name={`question-${question.id}`}
                        checked={answers[question.id] === optionIndex}
                        onChange={() => setAnswers((prev) => ({ ...prev, [question.id]: optionIndex }))}
                        disabled={submitting}
                      />{' '}
                      {option}
                    </label>
                  ))}
                </div>
              )}
            </div>
          ))}

          {submitError ? <Banner tone='error'>{submitError}</Banner> : null}

          <Button variant='primary' onClick={() => setConfirmOpen(true)} disabled={submitting}>
            {submitting ? 'Đang nộp...' : 'Nộp bài'}
          </Button>
        </Card>
      ) : null}

      <Modal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title='Xác nhận nộp bài'
        footer={(
          <>
            <Button onClick={() => setConfirmOpen(false)} disabled={submitting}>Hủy</Button>
            <Button variant='primary' onClick={() => submitAttempt(false)} disabled={submitting}>
              {submitting ? 'Đang nộp...' : 'Xác nhận nộp'}
            </Button>
          </>
        )}
      >
        <p>Bạn đã trả lời {answeredCount}/{questions.length} câu. Bạn chắc chắn muốn nộp bài?</p>
      </Modal>
    </div>
  );
}
