import { useEffect, useState } from 'react';
import { apiJson } from '../lib/api';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Input from '../ui/Input';
import Badge from '../ui/Badge';
import Spinner from '../ui/Spinner';

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
    }
    finally { setTopicsLoading((p)=>({ ...p, [did]: false })); }
  };

  const onDelete = async (id) => { if (!window.confirm('Xóa tài liệu này?')) return; await apiJson(`/documents/${id}`, { method: 'DELETE' }); await refresh(); };
  const onRegen = async (id) => { setMsg('Đang regenerate topics...'); await apiJson(`/documents/${id}/topics/regenerate`, { method: 'POST' }); await loadTopics(id, true); await refresh(); setMsg('Đã regenerate topics.'); };
  const saveEdit = async (id) => { await apiJson(`/documents/${id}`, { method:'PUT', body: { title: editTitle, tags: editTags } }); setEditingId(null); await refresh(); };

  return (
    <div style={{ display:'grid', gap: 12 }}>
      <Card>
        <h2 style={{ marginTop:0 }}>Thư viện tài liệu</h2>
        {error ? <p style={{ color: 'var(--danger)' }}>{error}</p> : null}
        {msg ? <p>{msg}</p> : null}
      </Card>

      {docs.map((d) => (
        <Card key={d.document_id}>
          <div style={{ display:'flex', justifyContent:'space-between', gap:8, flexWrap:'wrap' }}>
            <div>
              <div style={{ fontWeight:800 }}>{d.title}</div>
              <div style={{ color:'var(--muted)', fontSize:14 }}>{d.filename} · chunks {d.chunk_count} · {d.created_at || ''}</div>
              <div style={{ color:'var(--muted)', fontSize:13 }}>Tags: {(d.tags || []).join(', ')}</div>
            </div>
            <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
              <Button onClick={()=>{ setEditingId(d.document_id); setEditTitle(d.title || ''); setEditTags((d.tags || []).join(', ')); }}>Edit</Button>
              <Button onClick={async ()=>{ const next = !topicsOpen[d.document_id]; setTopicsOpen((p)=>({ ...p, [d.document_id]: next })); if (next) await loadTopics(d.document_id); }}>View topics</Button>
              <Button onClick={()=>onRegen(d.document_id)}>Regenerate topics</Button>
              <Button onClick={()=>onDelete(d.document_id)}>Delete</Button>
            </div>
          </div>

          {editingId === d.document_id ? (
            <div style={{ marginTop:10, display:'grid', gap:8 }}>
              <Input value={editTitle} onChange={(e)=>setEditTitle(e.target.value)} placeholder='Title' />
              <Input value={editTags} onChange={(e)=>setEditTags(e.target.value)} placeholder='tags' />
              <div style={{ display:'flex', gap:8 }}><Button variant='primary' onClick={()=>saveEdit(d.document_id)}>Lưu</Button><Button onClick={()=>setEditingId(null)}>Hủy</Button></div>
            </div>
          ) : null}

          {topicsOpen[d.document_id] ? (
            <div style={{ marginTop:12, display:'grid', gap:10 }}>
              {topicsLoading[d.document_id] ? <Spinner /> : null}
              {(topicsByDoc[d.document_id] || []).map((t) => (
                <div key={t.topic_id || t.title} style={{ border:'1px solid var(--border)', borderRadius:12, padding:12 }}>
                  <div style={{ display:'flex', justifyContent:'space-between', gap:8 }}>
                    <b>{t.display_title || t.title}</b>
                    {t.quiz_ready ? <Badge tone='success'>Quiz-ready</Badge> : <Badge>Ít dữ liệu</Badge>}
                  </div>
                  {t.summary ? <p>{t.summary}</p> : null}
                  {t.study_guide_md ? (
                    <div style={{ border:'1px solid var(--border)', borderRadius:10, padding:10, background:'var(--surface-2)' }}>
                      <div style={{ whiteSpace:'pre-wrap', fontFamily:'inherit' }}>{t.study_guide_md}</div>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </Card>
      ))}
    </div>
  );
}
