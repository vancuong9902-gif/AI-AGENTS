import { useEffect, useMemo, useRef, useState } from 'react';
import { apiJson } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import PageContainer from '../ui/PageContainer';
import SectionHeader from '../ui/SectionHeader';
import Card from '../ui/Card';
import Input from '../ui/Input';
import Button from '../ui/Button';
import EmptyState from '../ui/EmptyState';
import LoadingState from '../ui/LoadingState';
import ErrorState from '../ui/ErrorState';
import './unified-pages.css';

export default function Tutor() {
  const { userId } = useAuth();
  const [question, setQuestion] = useState('');
  const [topic, setTopic] = useState('');
  const [docs, setDocs] = useState([]);
  const [docId, setDocId] = useState('');
  const [messages, setMessages] = useState([]);
  const [rightSuggestions, setRightSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [docsLoading, setDocsLoading] = useState(true);
  const [error, setError] = useState('');
  const [learningPlan, setLearningPlan] = useState(null);
  const questionInputRef = useRef(null);

  const storageKey = useMemo(() => `tutor_conv_${userId ?? 1}_${docId || 'auto'}`, [userId, docId]);

  useEffect(() => {
    (async () => {
      setDocsLoading(true);
      try {
        const data = await apiJson('/documents?limit=100&offset=0');
        const arr = data?.documents || data || [];
        const data = await apiJson("/documents?limit=100&offset=0");
        const arr = Array.isArray(data?.items) ? data.items : data?.documents || [];
        setDocs(arr);
        if (!docId && arr.length > 0) {
          const saved = localStorage.getItem('active_document_id');
          setDocId(saved || String(arr[0].document_id));
        }
      } catch {
        // ignore
      } finally {
        setDocsLoading(false);
      }
    })();
  }, [docId]);

  useEffect(() => {
    (async () => {
      try {
        const data = await apiJson(`/lms/student/${userId ?? 1}/my-path`);
        setLearningPlan(data || null);
      } catch {
        setLearningPlan(null);
      }
    })();
  }, [userId]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      const parsed = raw ? JSON.parse(raw) : [];
      setMessages(Array.isArray(parsed) ? parsed : []);
    } catch {
      setMessages([]);
    }
  }, [storageKey]);

  useEffect(() => {
    localStorage.setItem(storageKey, JSON.stringify(messages));
  }, [messages, storageKey]);

  const formatCitationPage = (c) => {
    const ps = c?.page_start;
    const pe = c?.page_end;
    if (Number.isInteger(ps) && Number.isInteger(pe)) return ps === pe ? `Trang ${ps}` : `Trang ${ps}–${pe}`;
    if (Number.isInteger(ps)) return `Trang ${ps}`;
    return '';
  };

  const ask = async (overrideQuestion) => {
    const q = ((overrideQuestion ?? question) || '').trim();
    if (!q || loading) return;
    setError('');
    setLoading(true);
    setMessages((prev) => [...prev, { role: 'user', text: q }]);
    setQuestion('');
    try {
      const data = await apiJson('/tutor/chat', {
        method: 'POST',
        body: {
          user_id: userId ?? 1,
          question: q,
          topic: (topic || '').trim() || null,
          top_k: 6,
          document_ids: docId ? [Number(docId)] : null,
          allowed_topics: Array.isArray(learningPlan?.topics) ? learningPlan.topics : [],
        },
      });
      const isOffTopic = data?.is_off_topic === true || data?.off_topic === true;
      const politeOffTopic = 'Mình chưa thấy nội dung này trong tài liệu lớp. Bạn thử hỏi theo đúng chương/mục…';
      const answer = isOffTopic ? politeOffTopic : (data?.answer_md || data?.answer || '(Không có câu trả lời)');
      const suggested = data?.suggested_questions || data?.follow_up_questions || [];
      setRightSuggestions(Array.isArray(suggested) ? suggested.slice(0, 5) : []);

      let meta = data || {};
      const sourceIds = Array.isArray(data?.sources)
        ? data.sources.map((x) => Number(x?.chunk_id)).filter((x) => Number.isInteger(x) && x > 0)
        : [];
      if (sourceIds.length > 0) {
        try {
          const cites = await apiJson(`/documents/chunks/citations?chunk_ids=${sourceIds.join(',')}`);
          const map = {};
          (Array.isArray(cites) ? cites : []).forEach((c) => {
            if (Number.isInteger(c?.chunk_id)) map[c.chunk_id] = c;
          });
          meta = { ...meta, citation_map: map };
        } catch {
          // ignore citation failures
        }
      }

      setMessages((prev) => [...prev, { role: 'assistant', text: answer, meta, offTopic: isOffTopic }]);
    } catch (e) {
      const msg = e?.message || 'Tutor lỗi';
      setError(msg);
      setMessages((prev) => [...prev, { role: 'assistant', text: `❌ ${msg}`, meta: {} }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageContainer className='stack-md'>
      <SectionHeader title='🤖 Virtual AI Tutor' subtitle='Hỏi đáp theo tài liệu lớp với giao diện thống nhất.' />

      <div className='tutor-layout'>
        <Card className='stack-md'>
          <div className='row'>
            <label className='input-wrap' htmlFor='tutor-doc'>
              <span className='input-label'>Tài liệu</span>
              <select id='tutor-doc' className='ui-select' value={docId} onChange={(e) => { const v = e.target.value; setDocId(v); localStorage.setItem('active_document_id', String(v)); }}>
                <option value=''>Tự động (theo topic)</option>
                {docs.map((d) => <option key={d.document_id} value={d.document_id}>{d.title} (id={d.document_id})</option>)}
              </select>
            </label>
            <Input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder='(Tuỳ chọn) Topic...' label='Topic' />
          </div>

          <div className='tutor-chat'>
            {messages.length === 0 ? <EmptyState title='Bắt đầu cuộc trò chuyện' description='Đặt một câu hỏi để Tutor hỗ trợ bạn.' icon='💬' /> : null}
            {messages.map((m, idx) => (
              <div key={idx} className={`tutor-bubble ${m.role === 'user' ? 'user' : 'assistant'}`}>
                <div className='tutor-bubble-role'>{m.role === 'user' ? 'Bạn' : m.offTopic ? '⚠️ Tutor' : 'Tutor'}</div>
                <div className='tutor-message-text'>{m.text}</div>

                {m.role === 'assistant' && Array.isArray(m.meta?.sources) && m.meta.sources.length > 0 && (
                  <details>
                    <summary>📚 Sources</summary>
                    <ul>
                      {m.meta.sources.map((s, i) => (
                        <li key={`${s.chunk_id}-${i}`}>
                          <b>Chunk #{s.chunk_id}</b>{m.meta?.citation_map?.[s?.chunk_id] ? ` · ${formatCitationPage(m.meta.citation_map[s.chunk_id])}` : ''} (score {Number(s.score || 0).toFixed(2)}): {s.preview}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}

                {m.role === 'assistant' && Array.isArray(m.meta?.follow_up_questions) && m.meta.follow_up_questions.length > 0 && (
                  <div className='row'>
                    {m.meta.follow_up_questions.slice(0, 3).map((fq, i) => (
                      <Button key={i} type='button' variant='ghost' onClick={() => ask(fq)}>{fq}</Button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          {error ? <ErrorState title='Tutor đang gặp lỗi' description={error} /> : null}

          <div className='tutor-input-row'>
            <Input
              id='tutor-question'
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  ask();
                }
              }}
              placeholder='Nhập câu hỏi...'
            />
            <Button onClick={() => ask()} disabled={loading} variant='primary'>
              {loading ? 'Đang hỏi…' : 'Gửi'}
            </Button>
          </div>
        </Card>

        <Card className='tutor-aside stack-sm'>
          <h3>Panel gợi ý</h3>
          <div className='text-muted'>Topic hiện tại</div>
          <strong>{(topic || '').trim() || '(đang theo tài liệu đã chọn)'}</strong>
          <div className='text-muted'>Suggested questions</div>
          {docsLoading ? <LoadingState title='Đang tải tài liệu...' compact /> : null}
          {!docsLoading && (rightSuggestions || []).length === 0 ? <EmptyState title='Chưa có gợi ý' description='Gửi một câu hỏi để nhận gợi ý tiếp theo.' icon='✨' /> : null}
          {(rightSuggestions || []).map((sq, i) => (
            <Button key={i} type='button' variant='secondary' onClick={() => ask(sq)} className='text-left'>{sq}</Button>
          ))}
        </Card>
      </div>
    </PageContainer>
  );
}
