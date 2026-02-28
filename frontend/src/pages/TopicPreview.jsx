import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { apiJson } from '../lib/api';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Badge from '../ui/Badge';
import Banner from '../ui/Banner';
import Input from '../ui/Input';
import Modal from '../ui/Modal';
import PageHeader from '../ui/PageHeader';

const toneByConfidence = {
  high: 'success',
  medium: 'warning',
  low: 'danger',
};

export default function TopicPreview() {
  const { docId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [topics, setTopics] = useState([]);
  const [selectedTopicId, setSelectedTopicId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [showExcerpt, setShowExcerpt] = useState({});
  const [customOpen, setCustomOpen] = useState(false);
  const [customTitle, setCustomTitle] = useState('');
  const [customDescription, setCustomDescription] = useState('');

  const fetchPreview = async () => {
    setLoading(true);
    setError('');
    try {
      const resp = await apiJson(`/v1/documents/${docId}/topics/preview`);
      setData(resp || null);
      const loadedTopics = (resp?.topics || []).map((topic) => ({
        ...topic,
        titleDraft: topic?.title || '',
        localStatus: topic?.status || 'pending_review',
      }));
      setTopics(loadedTopics);
      setSelectedTopicId(loadedTopics?.[0]?.topic_id || null);
    } catch (e) {
      setError(e?.message || 'Không tải được topic preview.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPreview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId]);

  const selectedTopic = useMemo(() => topics.find((t) => t.topic_id === selectedTopicId) || null, [topics, selectedTopicId]);

  const markStatus = (topicId, status) => {
    setTopics((prev) => prev.map((item) => (item.topic_id === topicId ? { ...item, localStatus: status } : item)));
  };

  const updateTitle = (topicId, titleDraft) => {
    setTopics((prev) => prev.map((item) => (item.topic_id === topicId ? { ...item, titleDraft } : item)));
  };

  const approveAll = () => {
    setTopics((prev) => prev.map((item) => ({ ...item, localStatus: 'approved' })));
  };

  const addCustomTopic = async () => {
    if (!customTitle.trim()) return;
    try {
      await apiJson(`/v1/documents/${docId}/topics/add-custom`, {
        method: 'POST',
        body: {
          title: customTitle.trim(),
          description: customDescription.trim(),
        },
      });
      setCustomOpen(false);
      setCustomTitle('');
      setCustomDescription('');
      await fetchPreview();
    } catch (e) {
      setError(e?.message || 'Không thể thêm topic thủ công.');
    }
  };

  const submitConfirmation = async () => {
    setSaving(true);
    setError('');
    try {
      const approved = topics.filter((item) => item.localStatus === 'approved').map((item) => item.topic_id);
      const rejected = topics.filter((item) => item.localStatus === 'rejected').map((item) => item.topic_id);
      const renamedTopics = topics.reduce((acc, item) => {
        const original = (item.title || '').trim();
        const draft = (item.titleDraft || '').trim();
        if (draft && draft !== original) acc[String(item.topic_id)] = draft;
        return acc;
      }, {});

      await apiJson(`/v1/documents/${docId}/topics/confirm`, {
        method: 'POST',
        body: {
          approved_topic_ids: approved,
          rejected_topic_ids: rejected,
          renamed_topics: renamedTopics,
        },
      });
      navigate('/classroom');
    } catch (e) {
      setError(e?.message || 'Không thể xác nhận topic.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className='container grid-12'>
      <Card className='span-12'>
        <PageHeader title='Topic Preview' subtitle='Giáo viên duyệt topic trước khi học sinh thấy nội dung.' breadcrumbs={['Teacher', 'Topic Preview']} />
        {error ? <Banner tone='error'>{error}</Banner> : null}
      </Card>

      <Card className='span-7 stack-md'>
        <h2 className='section-title'>Danh sách topics</h2>
        {loading ? <Banner tone='info'>Đang tải danh sách topics...</Banner> : null}
        {!loading && !topics.length ? <Banner tone='warning'>Chưa có topic để duyệt.</Banner> : null}
        {!loading && topics.map((topic) => {
          const expanded = Boolean(showExcerpt[topic.topic_id]);
          return (
            <Card key={topic.topic_id} className='stack-sm' onClick={() => setSelectedTopicId(topic.topic_id)}>
              <div className='row' style={{ justifyContent: 'space-between' }}>
                <input
                  type='checkbox'
                  checked={topic.localStatus === 'approved'}
                  onChange={(e) => markStatus(topic.topic_id, e.target.checked ? 'approved' : 'rejected')}
                  onClick={(e) => e.stopPropagation()}
                />
                <Badge tone={toneByConfidence[topic.confidence] || 'warning'}>{topic.confidence || 'low'}</Badge>
                <Badge tone={topic.localStatus === 'approved' ? 'success' : topic.localStatus === 'rejected' ? 'danger' : 'warning'}>{topic.localStatus}</Badge>
              </div>

              <Input
                label='Title'
                value={topic.titleDraft}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => updateTitle(topic.topic_id, e.target.value)}
              />
              <div style={{ fontSize: 13 }}>{topic.summary || 'Không có tóm tắt.'}</div>
              <div className='stack-sm'>
                <div style={{ fontSize: 12, color: 'var(--muted)' }}>Sample excerpt:</div>
                <div style={{ background: 'var(--surface-2)', padding: 10, borderRadius: 10, fontSize: 13 }}>
                  {expanded ? (topic.sample_excerpt || 'Không có đoạn trích.') : `${(topic.sample_excerpt || '').slice(0, 120)}${(topic.sample_excerpt || '').length > 120 ? '...' : ''}`}
                </div>
                {(topic.sample_excerpt || '').length > 120 ? (
                  <Button className='ghost' onClick={(e) => { e.stopPropagation(); setShowExcerpt((prev) => ({ ...prev, [topic.topic_id]: !expanded })); }}>
                    {expanded ? 'Thu gọn' : 'Xem thêm'}
                  </Button>
                ) : null}
              </div>
              <div className='row'>
                <Button variant='primary' onClick={(e) => { e.stopPropagation(); markStatus(topic.topic_id, 'approved'); }}>✅ Duyệt</Button>
                <Button variant='danger' onClick={(e) => { e.stopPropagation(); markStatus(topic.topic_id, 'rejected'); }}>❌ Bỏ</Button>
              </div>
            </Card>
          );
        })}
      </Card>

      <Card className='span-5 stack-sm'>
        <h2 className='section-title'>Xem trước nội dung topic</h2>
        {!selectedTopic ? <Banner tone='info'>Chọn một topic ở cột trái để xem nội dung.</Banner> : (
          <>
            <h3 style={{ marginBottom: 0 }}>{selectedTopic.titleDraft || selectedTopic.title}</h3>
            <Badge tone='info'>{selectedTopic.page_hint}</Badge>
            <div style={{ fontSize: 13, color: 'var(--muted)' }}>Coverage: {Number(selectedTopic.coverage_score || 0).toFixed(2)}</div>
            <div style={{ background: 'var(--surface-2)', padding: 12, borderRadius: 12, minHeight: 180, whiteSpace: 'pre-wrap' }}>
              {selectedTopic.sample_excerpt || 'Không có đoạn trích từ PDF.'}
            </div>
            <div style={{ fontSize: 12, color: 'var(--muted)' }}>Từ khóa: {(selectedTopic.keywords || []).join(', ') || '—'}</div>
          </>
        )}
      </Card>

      <Card className='span-12'>
        <div className='row' style={{ justifyContent: 'space-between' }}>
          <div className='row'>
            <Button onClick={approveAll}>Duyệt tất cả</Button>
            <Button onClick={() => setCustomOpen(true)}>Thêm topic thủ công</Button>
          </div>
          <Button variant='primary' disabled={saving || !topics.length} onClick={submitConfirmation}>
            {saving ? 'Đang xác nhận...' : 'Xác nhận và Tiếp tục →'}
          </Button>
        </div>
        {data ? <div style={{ marginTop: 8, fontSize: 13, color: 'var(--muted)' }}>Tổng topics: {data.total_topics} · Chưa duyệt: {topics.filter((x) => x.localStatus === 'pending_review').length}</div> : null}
      </Card>

      <Modal
        open={customOpen}
        title='Thêm topic thủ công'
        onClose={() => setCustomOpen(false)}
        actions={(
          <>
            <Button onClick={() => setCustomOpen(false)}>Hủy</Button>
            <Button variant='primary' onClick={addCustomTopic}>Lưu topic</Button>
          </>
        )}
      >
        <div className='stack-sm'>
          <Input label='Tên topic' value={customTitle} onChange={(e) => setCustomTitle(e.target.value)} placeholder='Ví dụ: Ôn tập hàm số bậc nhất' />
          <label className='input-wrap'>
            <span className='input-label'>Mô tả</span>
            <textarea className='input' rows={4} value={customDescription} onChange={(e) => setCustomDescription(e.target.value)} placeholder='Mô tả ngắn cho topic thủ công...' />
          </label>
        </div>
      </Modal>
    </div>
  );
}
