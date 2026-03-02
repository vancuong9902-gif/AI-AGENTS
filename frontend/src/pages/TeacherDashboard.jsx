import React from 'react';
import Alert from '../components/Alert';
import { getErrorMessage, mvpApi } from '../api';
import LoadingSpinner from '../components/LoadingSpinner';

function levelClass(level) {
  const normalized = String(level || '').toLowerCase();
  if (normalized.includes('advanced')) return 'level-advanced';
  if (normalized.includes('intermediate')) return 'level-intermediate';
  return 'level-beginner';
}

export default function TeacherDashboard() {
  const [activeTab, setActiveTab] = React.useState('upload');
  const [courseId, setCourseId] = React.useState(null);
  const [topics, setTopics] = React.useState([]);
  const [exam, setExam] = React.useState(null);
  const [entryMessage, setEntryMessage] = React.useState('');
  const [results, setResults] = React.useState([]);
  const [page, setPage] = React.useState(1);
  const [total, setTotal] = React.useState(0);
  const [alert, setAlert] = React.useState({ type: 'info', message: '' });
  const [loading, setLoading] = React.useState(false);

  const pageSize = 10;

  const loadResults = React.useCallback(async (targetPage) => {
    setLoading(true);
    setAlert({ type: 'info', message: '' });
    try {
      const response = await mvpApi.getResults(targetPage, pageSize);
      const data = response.data.data;
      setResults(data.items || []);
      setTotal(data.pagination?.total || 0);
      setPage(data.pagination?.page || targetPage);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  }, []);

  const onUpload = async (file) => {
    if (!file) return;
    if (file.type !== 'application/pdf') {
      setAlert({ type: 'error', message: 'Please upload a PDF file only.' });
      return;
    }
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await mvpApi.uploadCourse(formData);
      setCourseId(response.data.data.course_id);
      setTopics([]);
      setExam(null);
      setEntryMessage('');
      setAlert({ type: 'success', message: 'PDF uploaded successfully.' });
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  const generateTopics = async () => {
    if (!courseId) return;
    setLoading(true);
    try {
      const response = await mvpApi.generateTopics(courseId);
      setTopics(response.data.data.topics || []);
      setAlert({ type: 'success', message: 'Generated topics successfully.' });
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  const generateExam = async () => {
    if (!courseId) return;
    setLoading(true);
    try {
      const response = await mvpApi.generateEntryTest(courseId);
      const payload = response.data.data;
      const questionCount = payload.questions?.length || 0;
      setExam(payload);
      setEntryMessage(`Entry test ready with ${questionCount} questions.`);
      setAlert({ type: 'success', message: 'Generated entry test successfully.' });
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    if (activeTab === 'results') {
      loadResults(1);
    }
  }, [activeTab, loadResults]);

  return (
    <div className="shell stack">
      <h1>Teacher Dashboard</h1>
      <Alert type={alert.type} message={alert.message} />
      <div className="tabs">
        <button className={`tab ${activeTab === 'upload' ? 'active' : ''}`} onClick={() => setActiveTab('upload')}>Upload & Generate</button>
        <button className={`tab ${activeTab === 'results' ? 'active' : ''}`} onClick={() => setActiveTab('results')}>View Results</button>
      </div>

      {activeTab === 'upload' && (
        <div className="card stack">
          <input type="file" accept="application/pdf" onChange={(e) => onUpload(e.target.files?.[0])} />
          {courseId && (
            <div className="teacher-checklist">
              <div className="checklist-item done">
                <span className="check-icon">✅</span>
                <span>Tài liệu đã upload</span>
              </div>
              <div className={`checklist-item ${topics.length > 0 ? 'done' : 'pending'}`}>
                <span className="check-icon">{topics.length > 0 ? '✅' : '⬜'}</span>
                <span>Nội dung khoá học {topics.length > 0 ? 'đã tạo' : 'chưa tạo'}</span>
              </div>
              <div className={`checklist-item ${exam ? 'done' : 'pending'}`}>
                <span className="check-icon">{exam ? '✅' : '⬜'}</span>
                <span>Bài kiểm tra đầu vào {exam ? 'đã tạo' : 'chưa tạo'}</span>
              </div>
            </div>
          )}
          <div className="row">
            <button disabled={!courseId || loading} onClick={generateTopics}>Generate Course Topics</button>
            <button disabled={!courseId || loading} onClick={generateExam}>Generate Entry Test</button>
          </div>
          {courseId && topics.length > 0 && exam && (
            <div className="ready-banner">🎉 Khoá học đã sẵn sàng! Học sinh có thể bắt đầu học và làm bài kiểm tra.</div>
          )}
          {entryMessage && <p>{entryMessage}</p>}
          <div className="stack">
            {topics.map((topic) => (
              <article key={topic.title} className="card">
                <h3>{topic.title}</h3>
                <p>{topic.summary}</p>
                <ul>{(topic.exercises || []).map((exercise) => <li key={exercise}>{exercise}</li>)}</ul>
              </article>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'results' && (
        <div className="card stack">
          {loading ? <LoadingSpinner label="Loading results..." /> : (
            <>
              <table className="results-table">
                <thead>
                  <tr><th>Student ID</th><th>Score</th><th>Level</th><th>Submitted At</th></tr>
                </thead>
                <tbody>
                  {results.length === 0 ? (
                    <tr><td colSpan="4">No results yet.</td></tr>
                  ) : results.map((row) => (
                    <tr key={row.result_id}>
                      <td>{row.student_id}</td>
                      <td>{row.score}</td>
                      <td><span className={`badge ${levelClass(row.level)}`}>{row.level}</span></td>
                      <td>{row.submitted_at || 'N/A'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="row">
                <button disabled={page <= 1} onClick={() => loadResults(page - 1)}>Previous</button>
                <span>Page {page}</span>
                <button disabled={page * pageSize >= total} onClick={() => loadResults(page + 1)}>Next</button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
