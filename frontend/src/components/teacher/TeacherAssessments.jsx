import React from 'react';
import { mvpApi, getErrorMessage } from '../../api';

const defaultConfig = {
  numQuestions: 15,
  durationMinutes: 30,
  easyRatio: 40,
  mediumRatio: 35,
  hardRatio: 25,
};

export default function TeacherAssessments({ setAlert, workflow, setWorkflow }) {
  const [config, setConfig] = React.useState(defaultConfig);
  const [previewQuestions, setPreviewQuestions] = React.useState([]);
  const [publishing, setPublishing] = React.useState(false);

  const topics = workflow.topicsDraft;

  const toggleTopic = (id) => {
    setWorkflow((prev) => {
      const selected = prev.selectedTopicIds.includes(id)
        ? prev.selectedTopicIds.filter((topicId) => topicId !== id)
        : [...prev.selectedTopicIds, id];
      return { ...prev, selectedTopicIds: selected };
    });
  };

  const validateRatios = () => config.easyRatio + config.mediumRatio + config.hardRatio === 100;

  const loadPreview = async () => {
    if (!workflow.courseId) return;
    try {
      const res = await mvpApi.generateEntryTest(workflow.courseId);
      const questions = res.data?.data?.questions || [];
      setPreviewQuestions(questions.slice(0, 3));
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    }
  };

  React.useEffect(() => {
    if (workflow.topicsPublished) loadPreview();
  }, [workflow.topicsPublished]);

  const activateAssessment = async () => {
    if (!workflow.courseId || !workflow.selectedTopicIds.length) {
      setAlert({ type: 'error', message: '⚠️ Vui lòng chọn topic để kích hoạt bài kiểm tra.' });
      return;
    }
    if (!validateRatios()) {
      setAlert({ type: 'error', message: '⚠️ Tổng tỉ lệ 3 mức độ phải bằng 100%.' });
      return;
    }
    setPublishing(true);
    try {
      const res = await mvpApi.generateEntryTest(workflow.courseId);
      const exam = res.data?.data;
      setWorkflow((prev) => ({ ...prev, assessmentActivated: true, assessmentId: exam?.exam_id }));
      setAlert({ type: 'success', message: '✅ Đã kích hoạt bài kiểm tra đầu vào.' });
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setPublishing(false);
    }
  };

  return (
    <div className="stack">
      <div className="card stack">
        <h3 className="card-title">Bước 3 · Cấu hình bài kiểm tra đầu vào</h3>
        {!workflow.topicsPublished && <div className="alert warning">Cần publish topics ở bước 1 trước khi cấu hình bài kiểm tra.</div>}

        <div className="stack gap-sm">
          <label>Chọn topics (mặc định: tất cả)</label>
          <div className="chip-wrap">
            {topics.map((topic) => (
              <button
                key={topic.id}
                type="button"
                className={`chip ${workflow.selectedTopicIds.includes(topic.id) ? 'active' : ''}`}
                onClick={() => toggleTopic(topic.id)}
              >
                {topic.title}
              </button>
            ))}
          </div>
        </div>

        <div className="grid-2">
          <div className="form-group">
            <label>Số câu</label>
            <input type="number" min={5} max={50} value={config.numQuestions} onChange={(e) => setConfig((p) => ({ ...p, numQuestions: Number(e.target.value) }))} />
          </div>
          <div className="form-group">
            <label>Thời gian (phút)</label>
            <input type="number" min={5} max={120} value={config.durationMinutes} onChange={(e) => setConfig((p) => ({ ...p, durationMinutes: Number(e.target.value) }))} />
          </div>
          <div className="form-group">
            <label>Tỉ lệ dễ (%)</label>
            <input type="number" min={0} max={100} value={config.easyRatio} onChange={(e) => setConfig((p) => ({ ...p, easyRatio: Number(e.target.value) }))} />
          </div>
          <div className="form-group">
            <label>Tỉ lệ trung bình (%)</label>
            <input type="number" min={0} max={100} value={config.mediumRatio} onChange={(e) => setConfig((p) => ({ ...p, mediumRatio: Number(e.target.value) }))} />
          </div>
          <div className="form-group">
            <label>Tỉ lệ khó (%)</label>
            <input type="number" min={0} max={100} value={config.hardRatio} onChange={(e) => setConfig((p) => ({ ...p, hardRatio: Number(e.target.value) }))} />
          </div>
        </div>

        {!validateRatios() && <div className="alert warning">Tổng tỉ lệ hiện tại chưa bằng 100%.</div>}

        <div className="row">
          <button className="ghost" onClick={loadPreview} disabled={!workflow.topicsPublished}>Preview 3 câu hỏi mẫu</button>
          <button className="success-btn" onClick={activateAssessment} disabled={publishing || !workflow.topicsPublished}>
            Kích hoạt bài kiểm tra đầu vào
          </button>
        </div>
      </div>

      <div className="card stack">
        <div className="row-between">
          <h3 className="card-title">Preview câu hỏi mẫu</h3>
          <span className="badge blue">{previewQuestions.length}/3</span>
        </div>
        {previewQuestions.length === 0 ? (
          <div className="empty-state compact"><p>Nhấn "Preview 3 câu hỏi mẫu" để xem trước nội dung.</p></div>
        ) : (
          previewQuestions.map((question, index) => (
            <div key={index} className="sample-question">
              <p><strong>Câu {index + 1}:</strong> {question.question}</p>
              <ul>
                {(question.options || []).map((option, optionIndex) => <li key={optionIndex}>{option}</li>)}
              </ul>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
