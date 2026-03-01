import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiJson } from '../lib/api';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Input from '../ui/Input';
import Spinner from '../ui/Spinner';
import Banner from '../ui/Banner';
import PageHeader from '../ui/PageHeader';
import Skeleton from '../ui/Skeleton';
import EmptyState from '../ui/EmptyState';

export default function FileLibrary() {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [tagFilter, setTagFilter] = useState('');
  const activeClassroomId = Number(localStorage.getItem('teacher_active_classroom_id')) || null;

  const refresh = async () => {
    setLoading(true);
    try {
      setDocs((await apiJson('/documents'))?.documents || []);
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
    </div>
  );
}
