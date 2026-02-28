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

export default function FileLibrary() {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [tagFilter, setTagFilter] = useState('');

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
        <PageHeader title='Library' subtitle='Quản lý tài liệu và topics trước khi tạo placement/final quiz.' breadcrumbs={['Teacher', 'Library']} />
      </Card>

      <Card className='span-12 stack-md'>
        <div className='grid-12'>
          <div className='span-6'><Input label='Tìm kiếm' value={search} onChange={(e) => setSearch(e.target.value)} placeholder='Tên tài liệu hoặc file...' /></div>
          <div className='span-6'><Input label='Lọc theo tag' value={tagFilter} onChange={(e) => setTagFilter(e.target.value)} placeholder='python, toán, lớp 10...' /></div>
        </div>
        {loading ? <><Skeleton height={24} /><Skeleton height={24} /><Spinner /></> : null}
        {error ? <Banner tone='error'>{error}</Banner> : null}
        {!loading && !error && filtered.length === 0 ? (
          <Banner tone='info'>Thư viện chưa có tài liệu phù hợp. <Link to='/upload' style={{ color: 'var(--primary)' }}>Tải lên tài liệu</Link></Banner>
        ) : null}
        {!loading && !error && filtered.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table className='data-table'>
              <thead><tr><th>Title</th><th>Filename</th><th>Chunks</th><th>Tags</th><th>Actions</th></tr></thead>
              <tbody>
                {filtered.map((d) => (
                  <tr key={d.document_id}>
                    <td>{d.title}</td><td>{d.filename}</td><td>{d.chunk_count}</td><td>{(d.tags || []).join(', ') || '-'}</td>
                    <td style={{ display: 'flex', gap: 8 }}><Link to={`/teacher/documents/${d.document_id}/topic-review`}><Button>Review & Publish topics</Button></Link></td>
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
