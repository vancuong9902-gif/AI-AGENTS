import { useEffect, useState } from 'react';
import { apiJson } from '../lib/api';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Input from '../ui/Input';
import Badge from '../ui/Badge';
import Spinner from '../ui/Spinner';
import { Accordion, AccordionItem } from '../ui/Accordion';

export default function FilesPage() {
  const [docs, setDocs] = useState([]);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');
  const [topicsOpen, setTopicsOpen] = useState({});
  const [topicsByDoc, setTopicsByDoc] = useState({});
  const [topicsLoading, setTopicsLoading] = useState({});
  const [editingId, setEditingId] = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const [editTags, setEditTags] = useState('');

  const refresh = async () => setDocs((await apiJson('/documents'))?.documents || []);
  useEffect(() => { refresh().catch((e)=>setError(e?.message || 'Lỗi tải tài liệu')); }, []);

  const loadTopics = async (did, force=false) => {
    if (!force && topicsByDoc[did]) return;
    setTopicsLoading((p)=>({ ...p, [did]: true }));
    try {
      const data = await apiJson(`/documents/${did}/topics?detail=1`);
      setTopicsByDoc((p)=>({ ...p, [did]: data?.topics || [] }));
    } finally {
      setTopicsLoading((p)=>({ ...p, [did]: false }));
    }
  };

  const onDelete = async (id) => { if (!window.confirm('Xóa tài liệu này?')) return; await apiJson(`/documents/${id}`, { method: 'DELETE' }); await refresh(); };
  const onRegen = async (id) => { setMsg('Đang regenerate topics...'); await apiJson(`/documents/${id}/topics/regenerate`, { method: 'POST' }); await loadTopics(id, true); await refresh(); setMsg('Đã regenerate topics.'); };
  const saveEdit = async (id) => { await apiJson(`/documents/${id}`, { method:'PUT', body: { title: editTitle, tags: editTags } }); setEditingId(null); await refresh(); };

  return (
    <div className='container grid-12'>
      <Card className='span-12'>
        <h1>Thư viện tài liệu</h1>
        <p style={{ color: 'var(--muted)' }}>Quản lý tài liệu, xem topics chi tiết, regenerate và kiểm tra quiz-ready.</p>
        {error ? <p style={{ color: 'var(--danger)' }}>{error}</p> : null}
        {msg ? <p>{msg}</p> : null}
      </Card>

      <Card className='span-12'>
        <div style={{ overflowX: 'auto' }}>
          <table className='data-table'>
            <thead>
              <tr><th>Title</th><th>Filename</th><th>Created</th><th>Chunks</th><th>Tags</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.document_id}>
                  <td>{d.title}</td>
                  <td>{d.filename}</td>
                  <td>{d.created_at || '-'}</td>
                  <td>{d.chunk_count}</td>
                  <td>{(d.tags || []).join(', ') || '-'}</td>
                  <td>
                    <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                      <Button onClick={()=>{ setEditingId(d.document_id); setEditTitle(d.title || ''); setEditTags((d.tags || []).join(', ')); }}>Edit</Button>
                      <Button onClick={async ()=>{ const next = !topicsOpen[d.document_id]; setTopicsOpen((p)=>({ ...p, [d.document_id]: next })); if (next) await loadTopics(d.document_id); }}>View topics</Button>
                      <Button onClick={()=>onRegen(d.document_id)}>Regenerate</Button>
                      <Button className='danger' onClick={()=>onDelete(d.document_id)}>Delete</Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {editingId ? (
        <Card className='span-12'>
          <h2>Chỉnh sửa tài liệu #{editingId}</h2>
          <div className='grid-12' style={{ marginTop: 10 }}>
            <div className='span-6'><Input label='Title' value={editTitle} onChange={(e)=>setEditTitle(e.target.value)} /></div>
            <div className='span-6'><Input label='Tags' helper='Nhập dạng: tag1, tag2' value={editTags} onChange={(e)=>setEditTags(e.target.value)} /></div>
          </div>
          <div style={{ marginTop: 12, display:'flex', gap:8 }}><Button variant='primary' onClick={()=>saveEdit(editingId)}>Lưu</Button><Button onClick={()=>setEditingId(null)}>Hủy</Button></div>
        </Card>
      ) : null}

      {docs.map((d) => topicsOpen[d.document_id] ? (
        <Card className='span-12' key={`topics-${d.document_id}`}>
          <h2>Topics · {d.title}</h2>
          {topicsLoading[d.document_id] ? <Spinner /> : null}
          <Accordion>
            {(topicsByDoc[d.document_id] || []).map((t) => (
              <AccordionItem key={t.topic_id || t.title} title={t.display_title || t.title} right={t.quiz_ready ? <Badge tone='success'>Quiz-ready</Badge> : <Badge>Ít dữ liệu</Badge>}>
                {t.summary ? <p>{t.summary}</p> : null}
                {(t.study_guide_md || t.content_preview) ? (
                  <div style={{ border:'1px solid var(--border)', borderRadius:12, padding:12, background:'var(--surface-2)' }}>
                    {t.study_guide_md ? (
                      <div style={{ whiteSpace:'pre-wrap' }}>
                        {t.study_guide_md}
                      </div>
                    ) : <p style={{ margin: 0 }}>{t.content_preview}</p>}
                  </div>
                ) : null}
              </AccordionItem>
            ))}
          </Accordion>
        </Card>
      ) : null)}
    </div>
  );
}
