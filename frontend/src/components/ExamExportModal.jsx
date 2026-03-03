import React from 'react';
import { mvpApi, getErrorMessage, downloadBlob } from '../api';

function parseFilename(headers) {
  const disposition = headers?.['content-disposition'] || headers?.['Content-Disposition'] || '';
  const match = disposition.match(/filename="?([^";]+)"?/i);
  return match?.[1] || 'exam.docx';
}

export default function ExamExportModal({ open, classroomId, onClose, onAlert }) {
  const [loading, setLoading] = React.useState(false);
  const [topics, setTopics] = React.useState([]);
  const [form, setForm] = React.useState({
    num_versions: 1,
    questions_per_exam: 20,
    exam_type: 'multiple_choice',
    difficulty: 'mixed',
    topic_ids: [],
    include_answer_key: true,
  });

  React.useEffect(() => {
    if (!open || !classroomId) return;
    const run = async () => {
      setLoading(true);
      try {
        const res = await mvpApi.getExamTopics(classroomId);
        setTopics(res.data?.data || []);
      } catch (err) {
        onAlert?.({ type: 'error', message: getErrorMessage(err) });
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [open, classroomId, onAlert]);

  if (!open) return null;

  const onToggleTopic = (topicId) => {
    setForm((prev) => ({
      ...prev,
      topic_ids: prev.topic_ids.includes(topicId)
        ? prev.topic_ids.filter((id) => id !== topicId)
        : [...prev.topic_ids, topicId],
    }));
  };

  const submit = async () => {
    if (!classroomId) return;
    setLoading(true);
    try {
      const payload = {
        ...form,
        topic_ids: form.topic_ids.length ? form.topic_ids : null,
      };
      const res = await mvpApi.exportExamWord(classroomId, payload);
      const filename = parseFilename(res.headers);
      downloadBlob(res.data, filename);
      onAlert?.({ type: 'success', message: '✅ Tạo đề và tải về thành công.' });
      onClose?.();
    } catch (err) {
      onAlert?.({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">Xuất đề thi Word</div>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="stack">
          <div className="form-group">
            <label>Số lượng đề: {form.num_versions}</label>
            <input type="range" min={1} max={5} value={form.num_versions} onChange={(e) => setForm((p) => ({ ...p, num_versions: Number(e.target.value) }))} />
          </div>

          <div className="form-group">
            <label>Số câu mỗi đề</label>
            <input type="number" min={10} max={50} value={form.questions_per_exam} onChange={(e) => setForm((p) => ({ ...p, questions_per_exam: Number(e.target.value) }))} />
          </div>

          <div className="form-group">
            <label>Loại đề</label>
            <div className="row">
              <label><input type="radio" checked={form.exam_type === 'multiple_choice'} onChange={() => setForm((p) => ({ ...p, exam_type: 'multiple_choice' }))} /> Trắc nghiệm</label>
              <label><input type="radio" checked={form.exam_type === 'essay'} onChange={() => setForm((p) => ({ ...p, exam_type: 'essay' }))} /> Tự luận</label>
              <label><input type="radio" checked={form.exam_type === 'mixed'} onChange={() => setForm((p) => ({ ...p, exam_type: 'mixed' }))} /> Hỗn hợp</label>
            </div>
          </div>

          <div className="form-group">
            <label>Độ khó</label>
            <select value={form.difficulty} onChange={(e) => setForm((p) => ({ ...p, difficulty: e.target.value }))}>
              <option value="easy">Dễ</option>
              <option value="medium">Trung bình</option>
              <option value="hard">Khó</option>
              <option value="mixed">Tổng hợp</option>
            </select>
          </div>

          <div className="form-group">
            <label>Chủ đề (mặc định: tất cả)</label>
            {loading ? <small>Đang tải chủ đề...</small> : (
              <div className="stack">
                {topics.map((topic) => (
                  <label key={topic.id}>
                    <input type="checkbox" checked={form.topic_ids.includes(topic.id)} onChange={() => onToggleTopic(topic.id)} /> {topic.title}
                  </label>
                ))}
                {topics.length === 0 && <small>Không có chủ đề riêng, hệ thống sẽ lấy toàn bộ câu hỏi phù hợp.</small>}
              </div>
            )}
          </div>

          <div className="form-group">
            <label>
              <input
                type="checkbox"
                checked={form.include_answer_key}
                onChange={(e) => setForm((p) => ({ ...p, include_answer_key: e.target.checked }))}
              /> Kèm đáp án
            </label>
          </div>
        </div>

        <div className="modal-footer">
          <button className="ghost" onClick={onClose}>Hủy</button>
          <button disabled={loading} onClick={submit}>{loading ? 'Đang tạo...' : 'Tạo đề & Tải về'}</button>
        </div>
      </div>
    </div>
  );
}
