import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { apiJson } from '../lib/api';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Banner from '../ui/Banner';
import Input from '../ui/Input';
import PageHeader from '../ui/PageHeader';

export default function TopicPreview() {
  const { docId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [topics, setTopics] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const fetchPreview = async () => {
    setLoading(true);
    setError('');
    try {
      const resp = await apiJson(`/documents/${docId}/topics/preview`);
      setData(resp || null);
      const loaded = (resp?.topics || []).map((topic) => ({
        ...topic,
        approved: true,
        titleDraft: topic?.title || '',
      }));
      setTopics(loaded);
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

  const approvedCount = useMemo(() => topics.filter((t) => t.approved).length, [topics]);

  const updateTopic = (topicId, partial) => {
    setTopics((prev) => prev.map((item) => (item.id === topicId ? { ...item, ...partial } : item)));
  };

  const publishTopics = async () => {
    setSaving(true);
    setError('');
    try {
      const approved = topics
        .filter((t) => t.approved)
        .map((t) => ({
          id: t.id,
          ...(String(t.titleDraft || '').trim() && String(t.titleDraft || '').trim() !== String(t.title || '').trim() ? { title: String(t.titleDraft || '').trim() } : {}),
        }));
      const rejectedIds = topics.filter((t) => !t.approved).map((t) => t.id);

      await apiJson(`/documents/${docId}/topics/publish`, {
        method: 'POST',
        body: {
          approved,
          rejected_ids: rejectedIds,
        },
      });
      navigate('/library');
    } catch (e) {
      setError(e?.message || 'Không thể publish topics.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className='container grid-12'>
      <Card className='span-12'>
        <PageHeader title='Topic Preview' subtitle='Giáo viên duyệt topic trước khi publish cho học sinh.' breadcrumbs={['Teacher', 'Topic Preview']} />
        {error ? <Banner tone='error'>{error}</Banner> : null}
      </Card>

      <Card className='span-12 stack-md'>
        {loading ? <Banner tone='info'>Đang tải danh sách topics...</Banner> : null}
        {!loading && !topics.length ? <Banner tone='warning'>Không có draft topics để duyệt.</Banner> : null}

        {!loading && data ? (
          <div style={{ fontSize: 13, color: 'var(--muted)' }}>
            Tổng topics: {data.total_topics} · Ước lượng trang: {data.estimated_pages} · Cảnh báo ngắn: {data.quality_summary?.too_short_topics || 0}
          </div>
        ) : null}

        {!loading && topics.map((topic) => (
          <Card key={topic.id} className='stack-sm'>
            <div className='row' style={{ justifyContent: 'space-between', alignItems: 'center' }}>
              <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <input
                  type='checkbox'
                  checked={Boolean(topic.approved)}
                  onChange={(e) => updateTopic(topic.id, { approved: e.target.checked })}
                />
                <span>{topic.approved ? 'Approve' : 'Reject'}</span>
              </label>
              <div style={{ fontSize: 12, color: 'var(--muted)' }}>
                Chunks: {topic.start_chunk_index ?? '-'} → {topic.end_chunk_index ?? '-'}
              </div>
            </div>

            <Input
              label='Title'
              value={topic.titleDraft}
              onChange={(e) => updateTopic(topic.id, { titleDraft: e.target.value })}
            />

            <div style={{ fontSize: 13 }}>{topic.summary_preview || 'Không có tóm tắt.'}</div>

            {(topic.quality_warnings?.length || topic.encoding_detected) ? (
              <Banner tone='warning'>
                ⚠️ Warnings: {[...(topic.quality_warnings || []), ...(topic.encoding_detected ? [`encoding:${topic.encoding_detected}`] : [])].join(', ')}
              </Banner>
            ) : null}
          </Card>
        ))}

        {!loading && topics.length ? (
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Button variant='primary' disabled={saving} onClick={publishTopics}>
              {saving ? 'Đang publish...' : `✅ Publish (${approvedCount} topics)`}
            </Button>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
