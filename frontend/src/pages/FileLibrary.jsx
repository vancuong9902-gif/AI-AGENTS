import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiJson } from '../lib/api';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Input from '../ui/Input';
import Spinner from '../ui/Spinner';
import Banner from '../ui/Banner';
import PageHeader from '../ui/PageHeader';
import LoadingState from '../ui/LoadingState';
import ErrorState from '../ui/ErrorState';
import './unified-pages.css';
import Skeleton from '../ui/Skeleton';
import EmptyState from '../ui/EmptyState';
import Modal from '../ui/Modal';

export default function FileLibrary() {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [tagFilter, setTagFilter] = useState('');
  const [topicsModal, setTopicsModal] = useState({
    isOpen: false,
    loading: false,
    error: '',
    topics: [],
    documentId: null,
    documentTitle: '',
  });
  const activeClassroomId = Number(localStorage.getItem('teacher_active_classroom_id')) || null;

  const closeTopicsModal = () => {
    setTopicsModal((prev) => ({ ...prev, isOpen: false }));
  };

  const openTopicsModal = async (doc) => {
    setTopicsModal({
      isOpen: true,
      loading: true,
      error: '',
      topics: [],
      documentId: doc.document_id,
      documentTitle: doc.title || doc.filename || `Tài liệu #${doc.document_id}`,
    });

    try {
      const data = await apiJson(`/documents/${doc.document_id}/topics?limit=100&offset=0`);
      const rawTopics = Array.isArray(data) ? data : data?.topics || data?.items || [];
      const normalizedTopics = rawTopics.map((topic, idx) => ({
        id: topic?.topic_id || topic?.id || `${doc.document_id}-${idx}`,
        title: topic?.display_title || topic?.effective_title || topic?.title || topic?.name || `Chủ đề ${idx + 1}`,
        chunkCount: Number(topic?.chunk_span || topic?.chunk_count || topic?.notes_count || 0),
        summary: String(topic?.summary || topic?.sample_content || '').trim(),
      }));
      setTopicsModal((prev) => ({ ...prev, loading: false, topics: normalizedTopics }));
    } catch (e) {
      setTopicsModal((prev) => ({ ...prev, loading: false, error: e?.message || 'Không tải được danh sách chủ đề.' }));
    }
  };

  const retryTopicsModal = async () => {
    if (!topicsModal.documentId) return;
    await openTopicsModal({
      document_id: topicsModal.documentId,
      title: topicsModal.documentTitle,
      filename: topicsModal.documentTitle,
    });
  };

  const refresh = async () => {
    setLoading(true);
    try {
      {
      const docsResp = await apiJson('/documents?limit=100&offset=0');
      setDocs(Array.isArray(docsResp?.items) ? docsResp.items : docsResp?.documents || []);
      }
      setError('');
    } catch (e) {
      setError(e?.message || 'Lỗi tải tài liệu');
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { refresh(); }, []);

  const filtered = useMemo(() => docs.filter((d) => {
    const q = search.trim().toLowerCase();
    const t = tagFilter.trim().toLowerCase();
    const matchQ = !q || `${d.title} ${d.filename}`.toLowerCase().includes(q);
    const matchT = !t || (d.tags || []).some((x) => String(x).toLowerCase().includes(t));
    return matchQ && matchT;
  }), [docs, search, tagFilter]);

  return (
    <div className='container grid-12'>
      <Card className='span-12'>
        <PageHeader title='Thư viện tài liệu' subtitle='Quản lý tài liệu và chủ đề trước khi tạo bài kiểm tra.' breadcrumbs={['Giáo viên', 'Thư viện tài liệu']} />
      </Card>

      <Card className='span-12 stack-md'>
        <div className='grid-12'>
          <div className='span-6'><Input label='Tìm kiếm' value={search} onChange={(e) => setSearch(e.target.value)} placeholder='Tên tài liệu hoặc file...' /></div>
          <div className='span-6'><Input label='Lọc theo tag' value={tagFilter} onChange={(e) => setTagFilter(e.target.value)} placeholder='python, toán, lớp 10...' /></div>
        </div>
        {loading ? <><Skeleton height={24} /><Skeleton height={24} /><Spinner /></> : null}
        {error ? <Banner tone='error'>{error}</Banner> : null}
        {!loading && !error && filtered.length === 0 ? (
          <EmptyState icon='📁' title='Chưa có tài liệu phù hợp' description='Thử đổi bộ lọc hoặc tải thêm tài liệu mới.' actionLabel='Tải lên tài liệu' onAction={() => window.location.assign('/upload')} />
        ) : null}
        {!loading && !error && filtered.length > 0 ? (
          <div className='data-table-wrap'>
            <table className='data-table'>
              <thead><tr><th>Tiêu đề</th><th>Tệp</th><th>Số đoạn</th><th>Thẻ</th><th>Thao tác</th></tr></thead>
              <tbody>
                {filtered.map((d) => (
                  <tr key={d.document_id}>
                    <td>{d.title}</td><td>{d.filename}</td><td>{d.chunk_count}</td><td>{(d.tags || []).join(', ') || '-'}</td>
                    <td><div className='row'>
                      <Button onClick={() => openTopicsModal(d)}>Xem topics</Button>
                      <Link to={`/teacher/documents/${d.document_id}/topic-review`}><Button>Rà soát và công bố chủ đề</Button></Link>
                      <Link
                        to={activeClassroomId
                          ? `/teacher/classrooms/${activeClassroomId}/documents/${d.document_id}/topics`
                          : '/teacher/assessments'}
                      >
                        <Button variant='primary'>Quản lý chủ đề</Button>
                      </Link>
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>

      <Modal
        open={topicsModal.isOpen}
        title={`Topics: ${topicsModal.documentTitle}`}
        onClose={closeTopicsModal}
        actions={<Button onClick={closeTopicsModal}>Đóng</Button>}
      >
        {topicsModal.loading ? <LoadingState title='Đang tải topics...' compact /> : null}
        {!topicsModal.loading && topicsModal.error ? <ErrorState title='Không tải được danh sách chủ đề' description={topicsModal.error} /> : null}
        {topicsModal.loading ? <Spinner /> : null}
        {!topicsModal.loading && topicsModal.error ? (
          <div className='stack-sm'>
            <Banner tone='error'>{topicsModal.error}</Banner>
            <Button onClick={retryTopicsModal}>Thử lại</Button>
          </div>
        ) : null}
        {!topicsModal.loading && !topicsModal.error && topicsModal.topics.length === 0 ? (
          <EmptyState
            icon='🧩'
            title='Chưa có topics'
            description='Tài liệu này chưa có chủ đề nào để hiển thị.'
          />
        ) : null}
        {!topicsModal.loading && !topicsModal.error && topicsModal.topics.length > 0 ? (
          <div className='stack-sm'>
            {topicsModal.topics.map((topic) => (
              <Card key={topic.id} className='filelibrary-topic-card'>
                <div><strong>{topic.title}</strong></div>
                <div className='filelibrary-topic-meta'>Số chunks/notes: {topic.chunkCount}</div>
                {topic.summary ? <div>{topic.summary}</div> : <div className='filelibrary-topic-meta'>Chưa có mô tả ngắn.</div>}
                <div>
                  <Link to={`/documents/${topicsModal.documentId}/topics/${topic.id}`}><Button variant='ghost'>Mở/Chi tiết</Button></Link>
                </div>
              </Card>
            ))}
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
