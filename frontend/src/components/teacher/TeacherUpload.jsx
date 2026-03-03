import React from 'react';
import { mvpApi, getErrorMessage } from '../../api';

const POLL_TARGET = 90;

export default function TeacherUpload({ setAlert, workflow, setWorkflow, onContinue }) {
  const [loading, setLoading] = React.useState(false);
  const [progress, setProgress] = React.useState(0);
  const [fileName, setFileName] = React.useState('');
  const [newTopicTitle, setNewTopicTitle] = React.useState('');
  const fileRef = React.useRef();
  const pollingRef = React.useRef(null);

  const stopPolling = React.useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  React.useEffect(() => () => stopPolling(), [stopPolling]);

  const startPolling = React.useCallback(() => {
    stopPolling();
    setProgress(10);
    pollingRef.current = window.setInterval(async () => {
      setProgress((prev) => (prev >= POLL_TARGET ? prev : prev + 10));
      try {
        await mvpApi.getMyCourses();
      } catch {
        // best-effort polling fallback when backend does not expose dedicated upload status
      }
    }, 700);
  }, [stopPolling]);

  const onUpload = async (file) => {
    if (!file) return;
    if (file.type !== 'application/pdf') {
      setAlert({ type: 'error', message: '⚠️ Chỉ chấp nhận file PDF.' });
      return;
    }

    setFileName(file.name);
    setLoading(true);
    setProgress(0);
    startPolling();

    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await mvpApi.uploadCourse(fd);
      const courseId = res.data?.data?.course_id;

      stopPolling();
      setProgress(100);
      setWorkflow((prev) => ({
        ...prev,
        courseId,
        uploadReady: true,
        topicsPublished: false,
        topicsDraft: [],
        selectedTopicIds: [],
      }));
      setAlert({ type: 'success', message: `✅ Đã tải lên "${file.name}" thành công. Bắt đầu phân tích chủ đề.` });

      if (courseId) {
        const topicsRes = await mvpApi.generateTopics(courseId);
        const fetchedTopics = topicsRes.data?.data?.topics || [];
        const normalizedTopics = fetchedTopics.map((topic, index) => ({
          id: index + 1,
          title: topic.title,
          summary: topic.summary,
          exercises: topic.exercises || [],
        }));
        setWorkflow((prev) => ({
          ...prev,
          topicsDraft: normalizedTopics,
          selectedTopicIds: normalizedTopics.map((topic) => topic.id),
        }));
      }
    } catch (err) {
      stopPolling();
      setProgress(0);
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  const updateTopicTitle = (id, title) => {
    setWorkflow((prev) => ({
      ...prev,
      topicsDraft: prev.topicsDraft.map((topic) => (topic.id === id ? { ...topic, title } : topic)),
    }));
  };

  const removeTopic = (id) => {
    setWorkflow((prev) => ({
      ...prev,
      topicsDraft: prev.topicsDraft.filter((topic) => topic.id !== id),
      selectedTopicIds: prev.selectedTopicIds.filter((topicId) => topicId !== id),
    }));
  };

  const addManualTopic = () => {
    const title = newTopicTitle.trim();
    if (!title) return;
    setWorkflow((prev) => {
      const nextId = prev.topicsDraft.length ? Math.max(...prev.topicsDraft.map((topic) => topic.id)) + 1 : 1;
      return {
        ...prev,
        topicsDraft: [...prev.topicsDraft, { id: nextId, title, summary: 'Topic thêm thủ công bởi giáo viên', exercises: [] }],
        selectedTopicIds: [...prev.selectedTopicIds, nextId],
      };
    });
    setNewTopicTitle('');
  };

  const publishTopics = () => {
    if (!workflow.topicsDraft.length) {
      setAlert({ type: 'error', message: '⚠️ Cần ít nhất 1 topic trước khi xuất bản.' });
      return;
    }
    setWorkflow((prev) => ({ ...prev, topicsPublished: true }));
    setAlert({ type: 'success', message: '✅ Topics đã được xác nhận và xuất bản cho học sinh.' });
    onContinue?.('class');
  };

  return (
    <div className="stack">
      <div className="card stack">
        <div>
          <h3 className="card-title">Bước 1 · Upload PDF & xác nhận topics</h3>
          <p className="card-sub">Kéo thả tài liệu PDF, chờ hệ thống phân tích và duyệt lại danh sách topics trước khi publish.</p>
        </div>

        <div
          className="file-drop"
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add('drag-over'); }}
          onDragLeave={(e) => e.currentTarget.classList.remove('drag-over')}
          onDrop={(e) => {
            e.preventDefault();
            e.currentTarget.classList.remove('drag-over');
            onUpload(e.dataTransfer.files[0]);
          }}
        >
          <div className="file-drop-icon">📄</div>
          <p><strong>Kéo thả</strong> hoặc <strong>click</strong> để tải PDF</p>
          {fileName && <p className="upload-file-name">📎 {fileName}</p>}
          <input
            ref={fileRef}
            type="file"
            accept="application/pdf"
            className="hidden-input"
            onChange={(e) => onUpload(e.target.files?.[0])}
          />
        </div>

        {(loading || progress > 0) && (
          <div className="stack gap-sm">
            <div className="row-between">
              <span className="card-sub">Tiến độ upload / xử lý</span>
              <strong>{progress}%</strong>
            </div>
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${progress}%` }} />
            </div>
          </div>
        )}
      </div>

      <div className="card stack">
        <div className="row-between">
          <h3 className="card-title">Preview topics (chờ xác nhận)</h3>
          <span className="badge gray">{workflow.topicsDraft.length} topics</span>
        </div>

        {workflow.topicsDraft.length === 0 ? (
          <div className="empty-state compact">
            <p>Upload PDF để sinh danh sách topics.</p>
          </div>
        ) : (
          <div className="stack gap-sm">
            {workflow.topicsDraft.map((topic) => (
              <div key={topic.id} className="topic-editor-row">
                <input value={topic.title} onChange={(e) => updateTopicTitle(topic.id, e.target.value)} />
                <button className="ghost sm" onClick={() => removeTopic(topic.id)}>Xóa</button>
              </div>
            ))}
          </div>
        )}

        <div className="row">
          <input
            value={newTopicTitle}
            onChange={(e) => setNewTopicTitle(e.target.value)}
            placeholder="Thêm topic thủ công"
          />
          <button className="ghost" onClick={addManualTopic}>+ Thêm topic</button>
        </div>

        <div className="row">
          <button className="success-btn" onClick={publishTopics} disabled={!workflow.topicsDraft.length || !workflow.uploadReady}>
            Xác nhận & Xuất bản
          </button>
          {workflow.topicsPublished && <span className="badge green">Đã publish cho học sinh</span>}
        </div>
      </div>
    </div>
  );
}
