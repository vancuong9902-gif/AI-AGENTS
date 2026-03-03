import React from 'react';
import { mvpApi, getErrorMessage } from '../../api';

const POLL_TARGET = 90;

export default function TeacherUpload({ setAlert, workflow, setWorkflow, onContinue }) {
  const [loading, setLoading] = React.useState(false);
  const [progress, setProgress] = React.useState(0);
  const [fileName, setFileName] = React.useState('');
  const [expandedTopicIds, setExpandedTopicIds] = React.useState([]);
  const [replaceFileId, setReplaceFileId] = React.useState(null);
  const fileRef = React.useRef();
  const pollingRef = React.useRef(null);

  const uploadedDocuments = workflow.uploadedDocuments || [];

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

  const onUpload = async (file, mode = 'append', targetDocId = null) => {
    if (!file) return;
    if (file.type !== 'application/pdf') {
      setAlert({ type: 'error', message: '⚠️ Chỉ chấp nhận file PDF.' });
      return;
    }

    const documentId = Date.now();
    const nextDoc = {
      id: documentId,
      filename: file.name,
      size: file.size,
      uploadedAt: new Date().toISOString(),
      status: 'processing',
    };

    setWorkflow((prev) => {
      const prevDocs = prev.uploadedDocuments || [];
      const withoutTarget = targetDocId ? prevDocs.filter((doc) => doc.id !== targetDocId) : prevDocs;
      const mergedDocs = mode === 'replace' ? [...withoutTarget, nextDoc] : [...withoutTarget, nextDoc];
      return {
        ...prev,
        uploadedDocuments: mergedDocs,
      };
    });

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
        uploadedDocuments: (prev.uploadedDocuments || []).map((doc) => (doc.id === documentId ? { ...doc, status: 'done' } : doc)),
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
          subtopics: topic.subtopics || topic.key_points || [],
          questions: topic.questions || [],
          learningObjectives: topic.learning_objectives || topic.learningObjectives || [],
        }));
        setWorkflow((prev) => ({
          ...prev,
          topicsDraft: normalizedTopics,
          selectedTopicIds: normalizedTopics.map((topic) => topic.id),
          uploadedDocuments: (prev.uploadedDocuments || []).map((doc) => (doc.id === documentId ? { ...doc, status: 'done' } : doc)),
        }));
      }
    } catch (err) {
      stopPolling();
      setProgress(0);
      setWorkflow((prev) => ({
        ...prev,
        uploadedDocuments: (prev.uploadedDocuments || []).map((doc) => (doc.id === documentId ? { ...doc, status: 'pending' } : doc)),
      }));
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
      setReplaceFileId(null);
    }
  };

  const updateTopicTitle = (id, title) => {
    setWorkflow((prev) => ({
      ...prev,
      topicsDraft: prev.topicsDraft.map((topic) => (topic.id === id ? { ...topic, title } : topic)),
    }));
  };

  const updateTopicSummary = (id, summary) => {
    setWorkflow((prev) => ({
      ...prev,
      topicsDraft: prev.topicsDraft.map((topic) => (topic.id === id ? { ...topic, summary } : topic)),
    }));
  };

  const toggleTopicExpand = (id) => {
    setExpandedTopicIds((prev) => (prev.includes(id) ? prev.filter((topicId) => topicId !== id) : [...prev, id]));
  };

  const removeDocument = (id) => {
    setWorkflow((prev) => ({
      ...prev,
      uploadedDocuments: (prev.uploadedDocuments || []).filter((doc) => doc.id !== id),
    }));
  };

  const formatFileSize = (size = 0) => {
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / (1024 * 1024)).toFixed(2)} MB`;
  };

  const formatUploadedDate = (value) => {
    if (!value) return '--';
    const date = new Date(value);
    return date.toLocaleString('vi-VN');
  };

  const statusMap = {
    pending: 'Chờ xử lý',
    processing: 'Đang xử lý',
    done: 'Hoàn tất',
  };

  const removeTopic = (id) => {
    setWorkflow((prev) => ({
      ...prev,
      topicsDraft: prev.topicsDraft.filter((topic) => topic.id !== id),
      selectedTopicIds: prev.selectedTopicIds.filter((topicId) => topicId !== id),
    }));
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
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (replaceFileId) {
                onUpload(file, 'replace', replaceFileId);
              } else {
                onUpload(file, 'append');
              }
              e.target.value = '';
            }}
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
            {workflow.topicsDraft.map((topic) => {
              const isExpanded = expandedTopicIds.includes(topic.id);
              return (
                <div key={topic.id} className={`topic-accordion ${isExpanded ? 'expanded' : ''}`}>
                  <button
                    type="button"
                    className="topic-accordion-trigger"
                    onClick={() => toggleTopicExpand(topic.id)}
                    aria-expanded={isExpanded}
                    aria-controls={`topic-panel-${topic.id}`}
                  >
                    <span className={`topic-chevron ${isExpanded ? 'expanded' : ''}`}>▸</span>
                    <span className="topic-accordion-title">{topic.title || `Topic ${topic.id}`}</span>
                  </button>
                  <button type="button" className="ghost sm" onClick={() => removeTopic(topic.id)}>Xóa</button>

                  <div id={`topic-panel-${topic.id}`} className="topic-accordion-panel">
                    <div className="topic-details stack gap-sm">
                      <label>
                        Tiêu đề topic
                        <input value={topic.title || ''} onChange={(e) => updateTopicTitle(topic.id, e.target.value)} />
                      </label>
                      <label>
                        Mô tả / tóm tắt
                        <textarea rows={3} value={topic.summary || ''} onChange={(e) => updateTopicSummary(topic.id, e.target.value)} />
                      </label>
                      <div>
                        <strong>Subtopics / Key points</strong>
                        {topic.subtopics?.length ? (
                          <ul>
                            {topic.subtopics.map((subtopic, index) => <li key={`${topic.id}-sub-${index}`}>{subtopic}</li>)}
                          </ul>
                        ) : (
                          <p className="card-sub">Chưa có subtopics từ API.</p>
                        )}
                      </div>
                      <div>
                        <strong>Bài tập gợi ý</strong>
                        {topic.exercises?.length ? (
                          <ul>
                            {topic.exercises.map((exercise, index) => <li key={`${topic.id}-exercise-${index}`}>{exercise}</li>)}
                          </ul>
                        ) : (
                          <p className="card-sub">Chưa có bài tập gợi ý.</p>
                        )}
                      </div>
                      <div>
                        <strong>Câu hỏi / Mục tiêu học tập</strong>
                        {(topic.questions?.length || topic.learningObjectives?.length) ? (
                          <ul>
                            {(topic.questions || []).map((question, index) => <li key={`${topic.id}-q-${index}`}>{question}</li>)}
                            {(topic.learningObjectives || []).map((objective, index) => <li key={`${topic.id}-o-${index}`}>{objective}</li>)}
                          </ul>
                        ) : (
                          <p className="card-sub">Chưa có dữ liệu câu hỏi hoặc mục tiêu học tập.</p>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="stack gap-sm document-manager">
          <div className="row-between">
            <h4 className="card-title">Quản lý tài liệu tải lên</h4>
            <button className="ghost sm" onClick={() => { setReplaceFileId(null); fileRef.current?.click(); }}>+ Tải thêm tài liệu</button>
          </div>

          {uploadedDocuments.length === 0 ? (
            <p className="card-sub">Chưa có tài liệu nào được tải lên.</p>
          ) : (
            <div className="stack gap-sm">
              {uploadedDocuments.map((doc) => (
                <div key={doc.id} className="document-row">
                  <div>
                    <div className="document-name">{doc.filename}</div>
                    <div className="card-sub">{formatFileSize(doc.size)} · {formatUploadedDate(doc.uploadedAt)}</div>
                  </div>
                  <span className={`badge ${doc.status === 'done' ? 'green' : 'gray'}`}>{statusMap[doc.status] || statusMap.pending}</span>
                  <div className="row gap-sm">
                    <button
                      className="ghost sm"
                      onClick={() => {
                        setReplaceFileId(doc.id);
                        fileRef.current?.click();
                      }}
                    >
                      Thay file
                    </button>
                    <button className="ghost sm" onClick={() => removeDocument(doc.id)}>Gỡ</button>
                  </div>
                </div>
              ))}
            </div>
          )}
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
