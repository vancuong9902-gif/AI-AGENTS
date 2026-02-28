import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE, apiJson } from '../lib/api';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Banner from '../ui/Banner';
import Spinner from '../ui/Spinner';
import Skeleton from '../ui/Skeleton';
import PageHeader from '../ui/PageHeader';

const MAX_FILE_SIZE = 50 * 1024 * 1024;

const isValidPdfFile = (candidate) => {
  if (!candidate) return 'Vui lòng chọn file PDF để tải lên.';
  if (!candidate.name?.toLowerCase().endsWith('.pdf')) return 'Chỉ chấp nhận file .pdf.';
  if (candidate.size > MAX_FILE_SIZE) return 'Dung lượng tối đa là 50MB.';
  return null;
};

const processingMessage = (status, progress) => {
  if (status === 'ready') return 'Sẵn sàng!';
  if (status === 'error') return 'Có lỗi khi xử lý tài liệu.';
  if (progress >= 70) return 'Đang nhận diện topic...';
  return 'Đang xử lý PDF...';
};

export default function Upload() {
  const navigate = useNavigate();
  const pollRef = useRef(null);

  const [file, setFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadedDoc, setUploadedDoc] = useState(null);
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [statusData, setStatusData] = useState(null);

  const stageText = useMemo(
    () => processingMessage(statusData?.status, statusData?.progress_pct ?? 0),
    [statusData],
  );

  useEffect(() => {
    if (!uploadedDoc?.doc_id) return undefined;

    pollRef.current = setInterval(async () => {
      try {
        const data = await apiJson(`/documents/${uploadedDoc.doc_id}/status`);
        setStatusData(data);
      } catch (e) {
        setError(e?.message || 'Không thể kiểm tra trạng thái xử lý.');
      }
    }, 2000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [uploadedDoc?.doc_id]);

  useEffect(() => {
    if (statusData?.status === 'ready' && uploadedDoc?.doc_id) {
      const timeout = setTimeout(() => navigate(`/topics/preview/${uploadedDoc.doc_id}`), 1000);
      return () => clearTimeout(timeout);
    }
    if (statusData?.status === 'ready' && pollRef.current) {
      clearInterval(pollRef.current);
    }
    return undefined;
  }, [navigate, statusData?.status, uploadedDoc?.doc_id]);

  const selectFile = (candidate) => {
    const validationError = isValidPdfFile(candidate);
    if (validationError) {
      setFile(null);
      setError(validationError);
      return;
    }
    setError(null);
    setFile(candidate);
  };

  const handleDrop = (event) => {
    event.preventDefault();
    setIsDragging(false);
    selectFile(event.dataTransfer.files?.[0] || null);
  };

  const handleUpload = async () => {
    const validationError = isValidPdfFile(file);
    if (validationError) {
      setError(validationError);
      return;
    }

    setUploading(true);
    setUploadProgress(0);
    setError(null);
    setStatusData({ status: 'pending', progress_pct: 0, topic_count: 0 });
    setUploadedDoc(null);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('user_id', localStorage.getItem('user_id') || '1');

    await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${API_BASE}/documents/upload`);
      xhr.setRequestHeader('Cache-Control', 'no-cache');
      const uid = localStorage.getItem('user_id');
      const role = localStorage.getItem('role');
      if (uid) xhr.setRequestHeader('X-User-Id', uid);
      if (role) xhr.setRequestHeader('X-User-Role', role);

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          setUploadProgress(Math.round((event.loaded / event.total) * 100));
        }
      };

      xhr.onload = () => {
        try {
          const body = JSON.parse(xhr.responseText || '{}');
          if (xhr.status >= 400) {
            throw new Error(body?.detail || body?.error?.message || 'Upload thất bại.');
          }
          setUploadProgress(100);
          setUploadedDoc(body?.data || body);
          resolve();
        } catch (e) {
          reject(e);
        }
      };

      xhr.onerror = () => reject(new Error('Không thể kết nối máy chủ.'));
      xhr.send(formData);
    }).catch((e) => {
      setError(e?.message || 'Upload thất bại, vui lòng thử lại.');
      setStatusData(null);
    }).finally(() => {
      setUploading(false);
    });
  };

  return (
    <div className='container grid-12'>
      <Card className='span-12'>
        <PageHeader title='Teacher Upload PDF' subtitle='Kéo thả hoặc chọn file PDF (tối đa 50MB).' breadcrumbs={['Teacher', 'Upload']} />
        {error ? <Banner tone='error'>{error}</Banner> : null}
      </Card>

      <Card className='span-8 stack-md'>
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          style={{
            border: isDragging ? '2px dashed var(--primary)' : '2px dashed var(--line)',
            borderRadius: 12,
            padding: 24,
            background: isDragging ? 'var(--bg-soft)' : 'transparent',
            textAlign: 'center',
          }}
        >
          <div style={{ fontWeight: 600 }}>Kéo & thả file PDF vào đây</div>
          <div style={{ color: 'var(--muted)', marginTop: 6 }}>hoặc</div>
          <input type='file' accept='.pdf,application/pdf' onChange={(e) => selectFile(e.target.files?.[0] || null)} style={{ marginTop: 12 }} />
          <div style={{ marginTop: 10, color: 'var(--muted)' }}>{file ? `Đã chọn: ${file.name}` : 'Chưa chọn file'}</div>
        </div>

        <Button variant='primary' disabled={!file || uploading} onClick={handleUpload}>
          {uploading ? 'Đang tải lên...' : 'Upload PDF'}
        </Button>

        {(uploading || uploadProgress > 0) ? (
          <div>
            <div style={{ height: 10, background: 'var(--line)', borderRadius: 999, overflow: 'hidden' }}>
              <div style={{ width: `${uploadProgress}%`, height: '100%', background: 'var(--primary)' }} />
            </div>
            <div style={{ marginTop: 8, color: 'var(--muted)' }}>Tiến độ upload: {uploadProgress}%</div>
          </div>
        ) : null}
      </Card>

      <Card className='span-4 stack-sm'>
        <h2 className='section-title'>Trạng thái xử lý</h2>
        {!statusData ? <Skeleton height={90} /> : null}
        {statusData ? (
          <>
            <Banner tone={statusData.status === 'error' ? 'error' : statusData.status === 'ready' ? 'success' : 'info'}>{stageText}</Banner>
            {(statusData.status === 'pending' || statusData.status === 'processing') ? <Spinner /> : null}
            <div>Progress: {statusData.progress_pct || 0}%</div>
            <div>Số topic: {statusData.topic_count || 0}</div>
            {statusData.status === 'ready' && uploadedDoc?.doc_id ? (
              <Button variant='primary' onClick={() => navigate(`/topics/preview/${uploadedDoc.doc_id}`)}>
                Xem topic đã phân tích →
              </Button>
            ) : null}
          </>
        ) : null}
      </Card>
    </div>
  );
}
