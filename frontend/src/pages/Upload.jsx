import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiJson } from '../lib/api';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Input from '../ui/Input';
import Badge from '../ui/Badge';
import Spinner from '../ui/Spinner';
import { Accordion, AccordionItem } from '../ui/Accordion';

export default function Upload() {
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState('');
  const [tags, setTags] = useState('');
  const [uploading, setUploading] = useState(false);
  const [hint, setHint] = useState('');
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const submitDisabled = !file || uploading;
  const parsedTags = useMemo(
    () => tags.split(',').map((tag) => tag.trim()).filter(Boolean),
    [tags],
  );

  const handleUpload = async (event) => {
    event.preventDefault();
    if (!file) {
      setHint('Vui lòng chọn file trước khi tải lên.');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('user_id', localStorage.getItem('user_id') || '1');
    if (title.trim()) formData.append('title', title.trim());
    if (tags.trim()) formData.append('tags', tags.trim());

    setUploading(true);
    setError('');
    setResult(null);
    setHint('Đang tải lên và xử lý tài liệu...');

    try {
      const data = await apiJson('/documents/upload', { method: 'POST', body: formData });
      setResult(data || null);
      setHint('Tải lên thành công.');
    } catch (err) {
      setError(err?.message || 'Upload thất bại, vui lòng thử lại.');
      setHint('');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className='container grid-12'>
      <Card className='span-12'>
        <h1>Upload tài liệu</h1>
        <p style={{ color: 'var(--muted)' }}>Hỗ trợ PDF/DOCX/PPTX. Với PDF dài, hệ thống sẽ ưu tiên coverage để tránh thiếu nội dung.</p>
      </Card>

      <Card className='span-6'>
        <h2 style={{ marginBottom: 10 }}>Biểu mẫu tải lên</h2>
        <form onSubmit={handleUpload} style={{ display: 'grid', gap: 12 }}>
          <Input label='Tiêu đề tài liệu' helper='Nên đặt theo môn/chương để dễ tìm.' value={title} onChange={(e) => setTitle(e.target.value)} placeholder='Ví dụ: Python cơ bản - Chương 1' />
          <Input label='Tags' helper='Nhập danh sách, ngăn cách bằng dấu phẩy.' value={tags} onChange={(e) => setTags(e.target.value)} placeholder='python, chương 1, căn bản' />
          <Input
            label='Tệp tài liệu'
            helper='Kích thước lớn có thể xử lý lâu hơn.'
            type='file'
            accept='.pdf,.docx,.pptx'
            onChange={(e) => {
              setFile(e.target.files?.[0] || null);
              setError('');
              setResult(null);
              setHint('');
            }}
          />

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <Button variant='primary' type='submit' disabled={submitDisabled}>{uploading ? 'Đang tải lên...' : 'Tải lên'}</Button>
            {uploading ? <Spinner /> : null}
            {!file ? <Badge>Chưa chọn file</Badge> : <Badge tone='success'>{file.name}</Badge>}
            {parsedTags.length ? <Badge tone='info'>{parsedTags.length} tags</Badge> : null}
          </div>
        </form>
        {hint ? <p style={{ marginBottom: 0 }}>{hint}</p> : null}
        {error ? <p style={{ color: 'var(--danger)', marginBottom: 0 }}>Lỗi: {error}</p> : null}
      </Card>

      <Card className='span-6'>
        <h2 style={{ marginBottom: 10 }}>Hướng dẫn xử lý khi topics chưa tốt</h2>
        <ul>
          <li>Nếu <b>topics_status ≠ OK</b>: thử Regenerate topics trong Thư viện.</li>
          <li>Nếu coverage thấp: kiểm tra lại PDF scan, cân nhắc OCR tốt hơn.</li>
          <li>Nếu quá ít topic: ưu tiên file có heading rõ hoặc tải bản chất lượng cao hơn.</li>
        </ul>
        <Link to='/teacher/files' style={{ color: 'var(--primary)', fontWeight: 600 }}>Mở Thư viện tài liệu →</Link>
      </Card>

      {result ? (
        <Card className='span-12'>
          <h2>Kết quả upload</h2>
          <div className='grid-12' style={{ marginTop: 10 }}>
            <div className='span-4'><b>Document ID:</b> {result?.document_id ?? 'N/A'}</div>
            <div className='span-4'><b>Filename:</b> {result?.filename || file?.name || 'N/A'}</div>
            <div className='span-4'><b>Chunk count:</b> {result?.chunk_count ?? 'N/A'}</div>
          </div>

          <Card style={{ marginTop: 12 }}>
            <h3>PDF extraction report</h3>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 6 }}>
              <Badge tone='info'>Extractor: {result?.pdf_report?.chosen_extractor || 'N/A'}</Badge>
              <Badge tone={result?.pdf_report?.ocr_used ? 'warning' : 'success'}>OCR: {result?.pdf_report?.ocr_used ? 'BẬT' : 'Tắt'}</Badge>
              <Badge>Candidates: {(result?.pdf_report?.candidates || []).length}</Badge>
            </div>
            {(result?.pdf_report?.candidates || []).length ? (
              <div style={{ overflowX: 'auto', marginTop: 10 }}>
                <table className='data-table'>
                  <thead><tr><th>Candidate</th><th>Quality</th><th>Coverage</th><th>Chars</th><th>Chunks</th></tr></thead>
                  <tbody>
                    {(result?.pdf_report?.candidates || []).map((c) => (
                      <tr key={c.name}>
                        <td>{c.name}</td>
                        <td>{c.quality_score ?? '-'}</td>
                        <td>{c.page_coverage ?? '-'}</td>
                        <td>{c.char_len ?? '-'}</td>
                        <td>{c.chunk_count ?? '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </Card>

          <div style={{ marginTop: 14 }}>
            <h3>Topics ({(result?.topics || []).length})</h3>
            {(result?.topics_status && result?.topics_status !== 'OK') ? (
              <p style={{ color: 'var(--warning)' }}>Topics status: {result?.topics_status} {result?.topics_reason ? `- ${result?.topics_reason}` : ''}</p>
            ) : null}
            <Accordion>
              {(result?.topics || []).map((topic, index) => (
                <AccordionItem
                  key={topic.topic_id || `${topic.title}-${index}`}
                  title={`${index + 1}. ${topic.display_title || topic.title}`}
                  right={topic.quiz_ready ? <Badge tone='success'>Quiz-ready</Badge> : <Badge>Ít dữ liệu</Badge>}
                >
                  <p>{topic.summary || 'Chưa có tóm tắt.'}</p>
                  <div><b>Keywords:</b> {(topic.keywords || []).join(', ') || 'N/A'}</div>
                  <div><b>Outline:</b> {(topic.outline || []).join(' • ') || 'N/A'}</div>
                  <div><b>Key points:</b> {(topic.key_points || []).join(' • ') || 'N/A'}</div>
                  <div><b>Definitions:</b> {(topic.definitions || []).join(' • ') || 'N/A'}</div>
                  <div><b>Examples:</b> {(topic.examples || []).join(' • ') || 'N/A'}</div>
                  <div><b>Formulas:</b> {(topic.formulas || []).join(' • ') || 'N/A'}</div>
                  {topic.content_preview ? <p style={{ marginBottom: 0, color: 'var(--muted)' }}>{topic.content_preview}</p> : null}
                </AccordionItem>
              ))}
            </Accordion>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
