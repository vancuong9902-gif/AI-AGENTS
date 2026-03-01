import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { apiJson } from '../lib/api';
import Card from '../ui/Card';
import Input from '../ui/Input';
import Button from '../ui/Button';
import Banner from '../ui/Banner';
import Badge from '../ui/Badge';
import PageHeader from '../ui/PageHeader';
import Spinner from '../ui/Spinner';

const FILTER_OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'quiz_ready', label: 'Quiz OK' },
  { value: 'too_short', label: 'Too short' },
];

function normalizeTopics(payload) {
  const raw = Array.isArray(payload) ? payload : payload?.topics || payload?.items || [];
  return (Array.isArray(raw) ? raw : []).map((topic, index) => {
    const title = String(topic?.display_title || topic?.title || topic?.name || `Topic ${index + 1}`).trim();
    const chunkSpan = String(topic?.chunk_span || topic?.chunk_range || '-').trim();
    const evidenceChunkSpan = String(topic?.evidence_chunk_span || topic?.evidence_range || '-').trim();

    const parsedChunkCount = Number(topic?.chunk_count ?? topic?.chunks ?? 0);
    const chunkCount = Number.isFinite(parsedChunkCount) ? parsedChunkCount : 0;

    const tooShort = Boolean(topic?.too_short) || (chunkCount > 0 && chunkCount < 2) || chunkSpan === '1' || chunkSpan === '1-1';
    return {
      key: `${title}-${topic?.topic_id || topic?.id || index}`,
      title,
      summary: String(topic?.summary || '').trim(),
      chunkSpan,
      evidenceChunkSpan,
      quizReady: Boolean(topic?.quiz_ready),
      tooShort,
    };
  });
}

export default function TopicSelection() {
  const { classroomId, documentId } = useParams();
  const [topics, setTopics] = useState([]);
  const [selectedTopics, setSelectedTopics] = useState([]);
  const [search, setSearch] = useState('');
  const [filterMode, setFilterMode] = useState('all');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [missingTopics, setMissingTopics] = useState([]);

  const storageKey = `teacher_selected_topics_${classroomId}_${documentId}`;

  useEffect(() => {
    const loadTopics = async () => {
      if (!documentId) return;
      setLoading(true);
      setError('');
      try {
        const data = await apiJson(`/documents/${documentId}/topics?detail=1`);
        const normalized = normalizeTopics(data);
        setTopics(normalized);

        const cachedRaw = localStorage.getItem(storageKey);
        if (!cachedRaw) {
          setSelectedTopics([]);
          return;
        }
        const cached = JSON.parse(cachedRaw);
        const cachedSet = new Set(Array.isArray(cached) ? cached : []);
        setSelectedTopics(normalized.map((topic) => topic.title).filter((title) => cachedSet.has(title)));
      } catch (e) {
        setError(e?.message || 'Không tải được danh sách topic.');
      } finally {
        setLoading(false);
      }
    };

    loadTopics();
  }, [documentId, storageKey]);

  const visibleTopics = useMemo(() => {
    const q = search.trim().toLowerCase();
    return topics.filter((topic) => {
      const matchesSearch = !q || `${topic.title} ${topic.summary}`.toLowerCase().includes(q);
      const matchesFilter =
        filterMode === 'all' ||
        (filterMode === 'quiz_ready' && topic.quizReady) ||
        (filterMode === 'too_short' && topic.tooShort);
      return matchesSearch && matchesFilter;
    });
  }, [topics, search, filterMode]);

  const selectedSet = new Set(selectedTopics);

  const toggleTopic = (title) => {
    setSelectedTopics((prev) => {
      const current = Array.isArray(prev) ? prev : [];
      if (current.includes(title)) return current.filter((item) => item !== title);
      return [...current, title];
    });
  };

  const selectAllVisible = () => {
    setSelectedTopics((prev) => {
      const combined = new Set([...(prev || []), ...visibleTopics.map((topic) => topic.title)]);
      return Array.from(combined);
    });
  };

  const clearAll = () => setSelectedTopics([]);

  const submitSelection = async () => {
    if (!classroomId || !documentId) return;
    setSaving(true);
    setError('');
    setSuccess('');
    setMissingTopics([]);

    try {
      const payload = {
        teacher_id: Number(localStorage.getItem('user_id')),
        classroom_id: Number(classroomId),
        document_id: Number(documentId),
        topics: selectedTopics,
      };
      const response = await apiJson('/lms/teacher/select-topics', {
        method: 'POST',
        body: payload,
      });

      localStorage.setItem(storageKey, JSON.stringify(selectedTopics));

      const missing = Array.isArray(response?.missing_topics) ? response.missing_topics : [];
      setMissingTopics(missing);
      setSuccess('Đã xác nhận lựa chọn topic cho lớp.');
    } catch (e) {
      setError(e?.message || 'Không thể xác nhận topic.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className='container grid-12'>
      <Card className='span-12'>
        <PageHeader
          title='Quản lý Topic'
          subtitle='Chọn topic từ tài liệu để dùng cho bước tạo bài kiểm tra.'
          breadcrumbs={['Teacher', 'Classroom', 'Topics']}
        />
        <div style={{ color: 'var(--muted)', fontSize: 13 }}>
          Classroom ID: <b>{classroomId}</b> · Document ID: <b>{documentId}</b>
        </div>
      </Card>

      <Card className='span-12 stack-md'>
        <div className='grid-12'>
          <div className='span-6'>
            <Input
              label='Tìm kiếm topic'
              placeholder='Tìm theo title hoặc summary...'
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className='span-6'>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 28 }}>
              {FILTER_OPTIONS.map((option) => (
                <Button
                  key={option.value}
                  variant={filterMode === option.value ? 'primary' : 'default'}
                  onClick={() => setFilterMode(option.value)}
                >
                  {option.label}
                </Button>
              ))}
            </div>
          </div>
        </div>

        <div className='row'>
          <Button onClick={selectAllVisible} disabled={!visibleTopics.length}>Chọn tất cả</Button>
          <Button onClick={clearAll} disabled={!selectedTopics.length}>Bỏ chọn tất cả</Button>
          <div style={{ color: 'var(--muted)', fontSize: 13 }}>
            Đã chọn {selectedTopics.length}/{topics.length} topic
          </div>
        </div>

        {loading ? <Spinner /> : null}
        {error ? <Banner tone='error'>{error}</Banner> : null}
        {success ? <Banner tone='success'>{success}</Banner> : null}
        {missingTopics.length > 0 ? (
          <Banner tone='warning'>
            Một số topic không tìm thấy trong backend: {missingTopics.join(', ')}
          </Banner>
        ) : null}

        {!loading && !error && visibleTopics.length === 0 ? (
          <Banner tone='info'>Không có topic phù hợp với bộ lọc hiện tại.</Banner>
        ) : null}

        {!loading && !error && visibleTopics.length > 0 ? (
          <div className='grid-12'>
            {visibleTopics.map((topic) => (
              <Card key={topic.key} className='span-6 stack-sm'>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
                  <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start', flex: 1 }}>
                    <input
                      type='checkbox'
                      checked={selectedSet.has(topic.title)}
                      onChange={() => toggleTopic(topic.title)}
                    />
                    <div>
                      <div style={{ fontWeight: 700 }}>{topic.title}</div>
                      {topic.summary ? <div style={{ color: 'var(--muted)', fontSize: 13 }}>{topic.summary}</div> : null}
                    </div>
                  </label>
                  <Badge tone={topic.quizReady ? 'success' : 'warning'}>{topic.quizReady ? 'Quiz OK' : 'Thiếu dữ liệu'}</Badge>
                </div>

                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', fontSize: 12 }}>
                  <Badge tone='info'>chunk_span: {topic.chunkSpan}</Badge>
                  <Badge tone='info'>evidence: {topic.evidenceChunkSpan}</Badge>
                </div>
              </Card>
            ))}
          </div>
        ) : null}

        <div className='row' style={{ justifyContent: 'space-between' }}>
          <Link to='/teacher/files'>← Quay lại thư viện</Link>
          <Button variant='primary' onClick={submitSelection} disabled={saving || selectedTopics.length === 0}>
            {saving ? 'Đang xác nhận...' : 'Xác nhận chọn Topic'}
          </Button>
        </div>
      </Card>
    </div>
  );
}
