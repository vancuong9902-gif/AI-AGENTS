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

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function StepRow({ done, label, hint }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '8px 0', borderBottom: '1px dashed var(--line)' }}>
      <span style={{ width: 18, lineHeight: '20px' }}>{done ? '✅' : '⬛'}</span>
      <div>
        <div style={{ fontWeight: 600 }}>{label}</div>
        {hint ? <div style={{ fontSize: 13, color: 'var(--muted)', marginTop: 2 }}>{hint}</div> : null}
      </div>
    </div>
  );
}

export default function Upload() {
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState('');
  const [tags, setTags] = useState('');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [status, setStatus] = useState(null);

  const parsedTags = useMemo(() => tags.split(',').map((tag) => tag.trim()).filter(Boolean), [tags]);

  const pollStatus = async (documentId) => {
    for (let i = 0; i < 12; i += 1) {
      try {
        const s = await apiJson(`/documents/${documentId}/status`);
        setStatus(s || null);
        if (s?.steps?.completed || s?.stage === 'completed') return s;
      } catch {
        // ignore transient polling errors
      }
      await sleep(1200);
    }
    return null;
  };

  const handleUpload = async (event) => {
    event.preventDefault();
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    formData.append('user_id', localStorage.getItem('user_id') || '1');
    if (title.trim()) formData.append('title', title.trim());
    if (tags.trim()) formData.append('tags', tags.trim());

    setUploading(true);
    setError('');
    setResult(null);
    setStatus({ stage: 'uploading', steps: { upload: false, parse_structure: false, extract_text: false, split_topics: false, completed: false } });

    try {
      const data = await apiJson('/documents/upload', { method: 'POST', body: formData });
      setResult(data || null);
      setStatus({
        stage: 'uploaded',
        ocr_used: !!data?.ocr_used,
        topics_count: data?.topics?.length || 0,
        steps: { upload: true, parse_structure: true, extract_text: true, split_topics: false, completed: false },
      });
      if (data?.document_id) await pollStatus(data.document_id);
    } catch (err) {
      setError(err?.message || 'Upload thất bại, vui lòng thử lại.');
    } finally {
      setUploading(false);
    }
  };

  const ocrUsed = !!(status?.ocr_used || result?.ocr_used || result?.pdf_report?.ocr_used);
  const topicsCount = status?.topics_count ?? result?.topics?.length ?? 0;

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
        <h2 className='section-title'>Điều hướng nhanh</h2>
        <Banner tone='info'>Theo dõi tiến trình xử lý, sau đó chuyển qua thư viện để rà soát topic.</Banner>
        <Link to='/teacher/files' style={{ color: 'var(--primary)', fontWeight: 700 }}>Xem thư viện tài liệu →</Link>
      </Card>

      {status ? (
        <Card className='span-8 stack-sm'>
          <h2 className='section-title'>Tiến trình xử lý</h2>
          <StepRow done={Boolean(status?.steps?.upload || result?.document_id)} label='Đang tải lên...' />
          <StepRow done={Boolean(status?.steps?.parse_structure)} label='Phân tích cấu trúc...' />
          <StepRow done={Boolean(status?.steps?.extract_text)} label='Trích xuất văn bản...' hint={ocrUsed ? 'Đang chạy OCR (có thể mất 1-2 phút)...' : ''} />
          <StepRow done={Boolean(status?.steps?.split_topics)} label='Chia topic...' />
          <StepRow done={Boolean(status?.steps?.completed)} label={status?.steps?.completed ? `Hoàn tất! ${topicsCount} topics đã được tạo` : 'Hoàn tất'} />
        </Card>
      ) : null}

      {status ? (
        <Card className='span-4 stack-sm'>
          <h2 className='section-title'>Kết quả nhanh</h2>
          <Badge tone={status?.steps?.completed ? 'success' : 'info'}>{status?.steps?.completed ? 'Đã xử lý xong' : 'Đang xử lý'}</Badge>
          <Badge>Topics: {topicsCount}</Badge>
          {ocrUsed ? <Banner tone='warning'>⚠️ PDF ảnh đã được OCR — chất lượng phụ thuộc độ rõ bản scan.</Banner> : null}
          {result?.document_id ? <Link to='/teacher/files' style={{ color: 'var(--primary)', fontWeight: 700 }}>Xem và chỉnh sửa topic →</Link> : null}
        </Card>
      ) : null}

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
