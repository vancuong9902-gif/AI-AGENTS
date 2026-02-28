import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiJson } from '../lib/api';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Input from '../ui/Input';
import Badge from '../ui/Badge';
import Spinner from '../ui/Spinner';

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
      const data = await apiJson('/documents/upload', {
        method: 'POST',
        body: formData,
      });
      setResult(data || null);
      setHint('Tải lên thành công. Bạn có thể vào Thư viện để xem chi tiết.');
    } catch (err) {
      setError(err?.message || 'Upload thất bại, vui lòng thử lại.');
      setHint('');
    } finally {
      setUploading(false);
    }
  };

  const extractorName = result?.pdf_report?.chosen_extractor || result?.pdf_report?.extractor_chosen || 'N/A';

  return (
    <div style={{ maxWidth: 980, margin: '0 auto', display: 'grid', gap: 16 }}>
      <Card>
        <h2 style={{ marginTop: 0, marginBottom: 8 }}>Upload tài liệu giáo viên</h2>
        <p style={{ marginTop: 0, opacity: 0.8 }}>
          Hỗ trợ định dạng <b>.pdf</b>, <b>.docx</b>, <b>.pptx</b>. Tags nhập theo dạng: <i>python, chương 1</i>.
        </p>

        <form onSubmit={handleUpload} style={{ display: 'grid', gap: 12 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
            <label style={{ display: 'grid', gap: 6 }}>
              <span>Tiêu đề tài liệu</span>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Ví dụ: Python cơ bản - Chương 1"
              />
            </label>

            <label style={{ display: 'grid', gap: 6 }}>
              <span>Tags</span>
              <Input
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="python, chuong 1"
              />
            </label>
          </div>

          <label style={{ display: 'grid', gap: 6 }}>
            <span>Chọn tệp</span>
            <Input
              type="file"
              accept=".pdf,.docx,.pptx"
              onChange={(e) => {
                setFile(e.target.files?.[0] || null);
                setError('');
                setResult(null);
              }}
            />
          </label>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            <Button variant="primary" type="submit" disabled={submitDisabled}>
              {uploading ? 'Đang tải lên...' : 'Tải lên'}
            </Button>
            {uploading ? <Spinner /> : null}
            {!file ? <Badge>Chưa chọn file</Badge> : <Badge tone="success">{file.name}</Badge>}
            {parsedTags.length ? <Badge tone="success">{parsedTags.length} tag</Badge> : null}
          </div>
        </form>

        {hint ? <p style={{ marginBottom: 0 }}>{hint}</p> : null}
        {error ? <p style={{ color: '#b91c1c', marginBottom: 0 }}>Lỗi: {error}</p> : null}
      </Card>

      {result ? (
        <Card>
          <h3 style={{ marginTop: 0 }}>Kết quả upload</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10 }}>
            <div><b>Document ID:</b> {result?.document_id ?? 'N/A'}</div>
            <div><b>Tên file:</b> {result?.filename || file?.name || 'N/A'}</div>
            <div><b>Số trang:</b> {result?.pdf_report?.page_count ?? 'N/A'}</div>
            <div><b>Extractor:</b> {extractorName}</div>
          </div>

          <div style={{ marginTop: 12, display: 'grid', gap: 8 }}>
            <b>PDF report tóm tắt</b>
            <div><b>Chunk count:</b> {result?.chunk_count ?? result?.pdf_report?.chunk_count ?? 'N/A'}</div>
            <div><b>Page coverage:</b> {result?.pdf_report?.page_coverage ?? 'N/A'}</div>
            <div><b>Candidates:</b> {(result?.pdf_report?.candidates || []).length}</div>
            {result?.pdf_report?.candidates?.length ? (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      <th align="left">Candidate</th>
                      <th align="left">Page coverage</th>
                      <th align="left">Chunk count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.pdf_report.candidates.map((candidate) => (
                      <tr key={candidate.name}>
                        <td>{candidate.name}</td>
                        <td>{candidate.page_coverage ?? '-'}</td>
                        <td>{candidate.chunk_count ?? '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>

          <div style={{ marginTop: 14 }}>
            <Link to="/teacher/files">Xem trong Thư viện tài liệu</Link>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
