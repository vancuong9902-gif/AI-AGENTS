import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiJson } from '../lib/api';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Input from '../ui/Input';
import Badge from '../ui/Badge';
import Spinner from '../ui/Spinner';
import Banner from '../ui/Banner';
import PageHeader from '../ui/PageHeader';

export default function Upload() {
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState('');
  const [tags, setTags] = useState('');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const parsedTags = useMemo(() => tags.split(',').map((tag) => tag.trim()).filter(Boolean), [tags]);

  const handleUpload = async (event) => {
    event.preventDefault();
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    formData.append('user_id', localStorage.getItem('user_id') || '1');
    if (title.trim()) formData.append('title', title.trim());
    if (tags.trim()) formData.append('tags', tags.trim());
    setUploading(true); setError(''); setResult(null);
    try {
      const data = await apiJson('/documents/upload', { method: 'POST', body: formData });
      setResult(data || null);
    } catch (err) {
      setError(err?.message || 'Upload thất bại, vui lòng thử lại.');
    } finally { setUploading(false); }
  };

  return (
    <div className='container grid-12'>
      <Card className='span-12'>
        <PageHeader title='Teacher Upload' subtitle='Tải tài liệu, xử lý nội dung và kiểm tra chất lượng extract trước khi tạo quiz.' breadcrumbs={['Teacher', 'Upload']} />
        {error ? <Banner tone='error'>{error}</Banner> : null}
      </Card>

      <Card className='span-7 stack-md'>
        <h2 className='section-title'>Tải tài liệu</h2>
        <form onSubmit={handleUpload} className='stack-md'>
          <Input label='Tiêu đề tài liệu' value={title} onChange={(e) => setTitle(e.target.value)} placeholder='Ví dụ: Python cơ bản - Chương 1' />
          <Input label='Tags' helper='Ngăn cách bằng dấu phẩy' value={tags} onChange={(e) => setTags(e.target.value)} placeholder='python, chương 1, căn bản' />
          <Input label='Tệp tài liệu' type='file' accept='.pdf,.docx,.pptx' onChange={(e) => setFile(e.target.files?.[0] || null)} />
          <div className='row'>
            <Button variant='primary' disabled={!file || uploading} type='submit'>{uploading ? 'Đang tải lên...' : 'Tải lên'}</Button>
            {uploading ? <Spinner /> : null}
            {file ? <Badge tone='success'>{file.name}</Badge> : <Badge>Chưa chọn file</Badge>}
            {!!parsedTags.length && <Badge tone='info'>{parsedTags.length} tags</Badge>}
          </div>
        </form>
      </Card>

      <Card className='span-5 stack-sm'>
        <h2 className='section-title'>Trạng thái & điều hướng</h2>
        <Banner tone='info'>Mọi màn đều có state rõ ràng: loading, error, empty và success.</Banner>
        <Link to='/teacher/files' style={{ color: 'var(--primary)', fontWeight: 700 }}>Xem thư viện tài liệu →</Link>
      </Card>

      {result ? (
        <Card className='span-12 stack-md'>
          <h2 className='section-title'>Kết quả upload</h2>
          <div className='row'>
            <Badge tone='info'>document_id: {result?.document_id ?? 'N/A'}</Badge>
            <Badge>{result?.filename || file?.name || 'N/A'}</Badge>
            <Badge>chunks: {result?.chunk_count ?? 'N/A'}</Badge>
            <Badge tone='success'>extractor: {result?.pdf_report?.extractor_chosen || result?.pdf_report?.chosen_extractor || 'N/A'}</Badge>
          </div>
          {result?.pdf_report?.selection_reason ? <Banner tone='success'>{result?.pdf_report?.selection_reason}</Banner> : null}
        </Card>
      ) : null}
    </div>
  );
}
