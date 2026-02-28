import { useState } from 'react';
import { apiJson } from '../lib/api';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Input from '../ui/Input';
import Badge from '../ui/Badge';
import Spinner from '../ui/Spinner';
import { AccordionItem } from '../ui/Accordion';

export default function Upload() {
  const [file, setFile] = useState(null);
  const [msg, setMsg] = useState('');
  const [title, setTitle] = useState('');
  const [tags, setTags] = useState('');
  const [uploading, setUploading] = useState(false);
  const [topics, setTopics] = useState([]);
  const [topicsStatus, setTopicsStatus] = useState(null);
  const [pdfReport, setPdfReport] = useState(null);

  const handleUpload = async () => {
    if (!file) return alert('Chọn file trước');
    const formData = new FormData();
    formData.append('file', file);
    formData.append('user_id', localStorage.getItem('user_id') || '1');
    if (title) formData.append('title', title);
    if (tags) formData.append('tags', tags);

    try {
      setUploading(true);
      setMsg('Đang upload và tách topic...');
      const res = await apiJson('/documents/upload', { method: 'POST', body: formData });
      setTopics(res?.topics || []);
      setTopicsStatus(res?.topics_status || null);
      setPdfReport(res?.pdf_report || null);
      setMsg((res?.topics || []).length > 0
        ? `Upload thành công. AI đã chia ${res.topics.length} topic.`
        : `Upload thành công nhưng topic chưa sẵn sàng (${res?.topics_status || 'N/A'}).`);
    } catch (err) {
      setMsg(err?.message || 'Không kết nối được backend');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div style={{ display: 'grid', gap: 14 }}>
      <Card>
        <h2 style={{ marginTop: 0 }}>Upload tài liệu giáo viên</h2>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <Input value={title} onChange={(e)=>setTitle(e.target.value)} placeholder='Tiêu đề tài liệu' />
          <Input value={tags} onChange={(e)=>setTags(e.target.value)} placeholder='Tags: python, chương 1' />
        </div>
        <div style={{ marginTop: 10, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <Input type='file' onChange={(e)=>setFile(e.target.files?.[0] || null)} />
          <Button variant='primary' onClick={handleUpload} disabled={uploading}>{uploading ? 'Đang xử lý...' : 'Upload'}</Button>
          {uploading ? <Spinner /> : null}
        </div>
        {msg ? <p>{msg}</p> : null}
        {topicsStatus ? <p>Topics status: <b>{topicsStatus}</b></p> : null}
        {topicsStatus && topicsStatus !== 'OK' ? <p style={{ color:'var(--warning)' }}>Gợi ý: thử PDF text-layer tốt hơn, bật OCR hoặc Regenerate topics trong thư viện.</p> : null}
      </Card>

      {pdfReport ? (
        <Card>
          <h3 style={{ marginTop: 0 }}>PDF extraction report</h3>
          <p>Extractor chọn: <b>{pdfReport?.chosen_extractor || 'N/A'}</b> · OCR used: <b>{String(!!pdfReport?.ocr_used)}</b></p>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead><tr><th align='left'>name</th><th>quality</th><th>chars</th><th>coverage</th><th>chunks</th></tr></thead>
              <tbody>
                {(pdfReport?.candidates || []).map((c) => (
                  <tr key={c.name}><td>{c.name}</td><td align='center'>{c.quality_score ?? '-'}</td><td align='center'>{c.char_len}</td><td align='center'>{c.page_coverage}</td><td align='center'>{c.chunk_count}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}

      {topics.length > 0 ? (
        <Card>
          <h3 style={{ marginTop: 0 }}>Topics chi tiết</h3>
          <div style={{ display: 'grid', gap: 10 }}>
            {topics.map((t) => (
              <AccordionItem key={t.topic_id || t.title} title={<div style={{display:'flex',justifyContent:'space-between'}}><span>{t.title}</span>{t.quiz_ready ? <Badge tone='success'>Quiz-ready</Badge> : <Badge>Ít dữ liệu</Badge>}</div>}>
                {t.summary ? <p>{t.summary}</p> : null}
                {!!t.keywords?.length && <p><b>Keywords:</b> {t.keywords.join(', ')}</p>}
                {!!t.outline?.length && <p><b>Outline:</b> {t.outline.slice(0, 8).join(' · ')}</p>}
                {!!t.key_points?.length && <ul>{t.key_points.slice(0, 8).map((x, i) => <li key={i}>{x}</li>)}</ul>}
                {!!t.definitions?.length && <ul>{t.definitions.slice(0, 6).map((d, i) => <li key={i}><b>{d.term}:</b> {d.definition}</li>)}</ul>}
                {!!t.examples?.length && <p><b>Ví dụ:</b> {t.examples.slice(0, 4).join(' | ')}</p>}
                {!!t.formulas?.length && <pre style={{ whiteSpace: 'pre-wrap' }}>{t.formulas.join('\n')}</pre>}
                {t.content_preview ? <p><b>Preview:</b> {t.content_preview}</p> : null}
              </AccordionItem>
            ))}
          </div>
        </Card>
      ) : null}
    </div>
  );
}
