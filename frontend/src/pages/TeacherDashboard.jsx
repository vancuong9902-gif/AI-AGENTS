import React from 'react';
import Alert from '../components/Alert';
import LoadingSpinner from '../components/LoadingSpinner';
import { mvpApi, downloadBlob, getErrorMessage } from '../api';
import { useAuth } from '../auth';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from 'recharts';

function levelClass(level) {
  const s = String(level || '').toLowerCase();
  if (s.includes('advanced')) return 'level-advanced';
  if (s.includes('intermediate')) return 'level-intermediate';
  return 'level-beginner';
}
function levelVN(level) {
  const s = String(level || '').toLowerCase();
  if (s.includes('advanced')) return 'Nâng cao';
  if (s.includes('intermediate')) return 'Trung bình';
  return 'Cơ bản';
}
const COLORS = ['#4f46e5', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];

function TabUpload({ setAlert }) {
  const [loading, setLoading] = React.useState(false);
  const [courseId, setCourseId] = React.useState(null);
  const [topics, setTopics] = React.useState([]);
  const [fileName, setFileName] = React.useState('');
  const [step, setStep] = React.useState(0);
  const [entryInfo, setEntryInfo] = React.useState(null);
  const fileRef = React.useRef();

  const onUpload = async (file) => {
    if (!file) return;
    if (file.type !== 'application/pdf') {
      setAlert({ type: 'error', message: '⚠️ Chỉ chấp nhận file PDF.' });
      return;
    }
    setFileName(file.name);
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await mvpApi.uploadCourse(fd);
      setCourseId(res.data.data.course_id);
      setTopics([]);
      setEntryInfo(null);
      setStep(1);
      setAlert({ type: 'success', message: `✅ Đã tải lên "${file.name}" thành công.` });
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
      const res = await mvpApi.generateTopics(courseId);
      setTopics(res.data.data.topics || []);
      setStep(2);
      setAlert({ type: 'success', message: `✅ Đã phân tích ${res.data.data.topics?.length || 0} chủ đề.` });
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  const generateEntryTest = async () => {
    if (!courseId) return;
    setLoading(true);
    try {
      const res = await mvpApi.generateEntryTest(courseId);
      const q = res.data.data.questions?.length || 0;
      setEntryInfo({ count: q });
      setAlert({ type: 'success', message: `✅ Đã tạo bài kiểm tra đầu vào với ${q} câu.` });
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="stack">
      <div className="row" style={{ gap: 8, flexWrap: 'nowrap' }}>
        {['📄 Tải PDF', '📚 Phân tích', '📝 Tạo đề'].map((s, i) => (
          <React.Fragment key={i}>
            <span style={{ fontWeight: step >= i ? 700 : 400, color: step >= i ? 'var(--primary)' : 'var(--gray-400)', fontSize: 13 }}>
              {s}
            </span>
            {i < 2 && <span style={{ color: 'var(--gray-300)' }}>→</span>}
          </React.Fragment>
        ))}
      </div>

      <div
        className="file-drop"
        onClick={() => fileRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add('drag-over'); }}
        onDragLeave={(e) => e.currentTarget.classList.remove('drag-over')}
        onDrop={(e) => { e.preventDefault(); e.currentTarget.classList.remove('drag-over'); onUpload(e.dataTransfer.files[0]); }}
      >
        <div className="file-drop-icon">📄</div>
        <p><strong>Kéo thả</strong> hoặc <strong>click</strong> để tải PDF</p>
        {fileName && <p style={{ color: 'var(--primary)', marginTop: 8 }}>📎 {fileName}</p>}
        {courseId && <span className="badge green" style={{ marginTop: 8 }}>✓ Đã tải lên</span>}
        <input ref={fileRef} type="file" accept="application/pdf" style={{ display: 'none' }} onChange={(e) => onUpload(e.target.files?.[0])} />
      </div>

      {courseId && (
        <div className="row">
          <button disabled={loading} onClick={generateTopics}>
            {loading ? '⏳ Đang phân tích...' : '📚 Phân tích chủ đề'}
          </button>
          <button className="success-btn" disabled={loading || !topics.length} onClick={generateEntryTest}>
            {loading ? '⏳...' : '📝 Tạo bài kiểm tra đầu vào'}
          </button>
        </div>
      )}

      {entryInfo && (
        <div className="alert success">
          🎉 Bài kiểm tra đầu vào đã sẵn sàng với <strong>{entryInfo.count} câu hỏi</strong> (3 mức độ khó). Học sinh có thể bắt đầu làm bài!
        </div>
      )}

      {topics.length > 0 && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">📋 {topics.length} Chủ đề từ tài liệu</span>
          </div>
          <div className="stack" style={{ gap: 8 }}>
            {topics.map((t, i) => (
              <div key={i} className="accordion-item">
                <div className="accordion-header">
                  <span>📌 {t.title}</span>
                  <span className="accordion-chevron">▼</span>
                </div>
                <div className="accordion-body" style={{ display: 'block' }}>
                  <p style={{ fontSize: 14, color: 'var(--gray-600)', marginBottom: 8 }}>{t.summary}</p>
                  {t.exercises?.length > 0 && (
                    <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: 'var(--gray-500)' }}>
                      {t.exercises.map((ex, j) => <li key={j}>{ex}</li>)}
                    </ul>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TabClassrooms({ setAlert }) {
  const [loading, setLoading] = React.useState(false);
  const [classrooms, setClassrooms] = React.useState([]);
  const [selected, setSelected] = React.useState(null);
  const [dashboard, setDashboard] = React.useState(null);
  const [showCreate, setShowCreate] = React.useState(false);
  const [form, setForm] = React.useState({ name: '', description: '' });

  const load = async () => {
    setLoading(true);
    try {
      const res = await mvpApi.getMyClassrooms();
      setClassrooms(res.data.classrooms || res.data || []);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => { load(); }, []);

  const createClass = async () => {
    if (!form.name.trim()) return;
    setLoading(true);
    try {
      await mvpApi.createClassroom(form.name, form.description);
      setShowCreate(false);
      setForm({ name: '', description: '' });
      setAlert({ type: 'success', message: '✅ Đã tạo lớp học.' });
      load();
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  const viewDashboard = async (cls) => {
    setSelected(cls);
    setLoading(true);
    try {
      const res = await mvpApi.getClassroomDashboard(cls.id);
      setDashboard(res.data);
    } catch {
      setDashboard(null);
    } finally {
      setLoading(false);
    }
  };

  const exportPDF = async (cls) => {
    try {
      const res = await mvpApi.exportClassReportPDF(cls.id);
      downloadBlob(res.data, `bao-cao-lop-${cls.name}.pdf`);
      setAlert({ type: 'success', message: '✅ Đã tải báo cáo PDF.' });
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    }
  };

  return (
    <div className="stack">
      <div className="row-between">
        <h2 style={{ fontSize: 18 }}>🏫 Quản lý lớp học</h2>
        <button onClick={() => setShowCreate(true)}>+ Tạo lớp mới</button>
      </div>

      {showCreate && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">Tạo lớp mới</span>
            <button className="ghost sm" onClick={() => setShowCreate(false)}>✕</button>
          </div>
          <div className="stack">
            <div className="form-group">
              <label>Tên lớp *</label>
              <input placeholder="VD: Toán 10A" value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} />
            </div>
            <div className="form-group">
              <label>Mô tả</label>
              <input placeholder="Mô tả ngắn về lớp học" value={form.description} onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))} />
            </div>
            <div className="row">
              <button onClick={createClass} disabled={loading || !form.name.trim()}>✅ Tạo lớp</button>
              <button className="ghost" onClick={() => setShowCreate(false)}>Hủy</button>
            </div>
          </div>
        </div>
      )}

      {loading && !classrooms.length ? <LoadingSpinner label="Đang tải..." /> : (
        classrooms.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🏫</div>
            <p>Chưa có lớp học nào. Hãy tạo lớp đầu tiên!</p>
          </div>
        ) : (
          <div className="grid-3">
            {classrooms.map((cls) => (
              <div key={cls.id} className="card" style={{ cursor: 'pointer' }}>
                <div className="card-header">
                  <div>
                    <div className="card-title">🏫 {cls.name}</div>
                    {cls.join_code && <span className="badge blue" style={{ marginTop: 4 }}>Mã: {cls.join_code}</span>}
                  </div>
                </div>
                <p style={{ fontSize: 13, color: 'var(--gray-400)', marginBottom: 12 }}>
                  {cls.description || 'Không có mô tả'}
                </p>
                <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
                  <button className="sm" onClick={() => viewDashboard(cls)}>📊 Xem dashboard</button>
                  <button className="sm ghost" onClick={() => exportPDF(cls)}>📄 Xuất PDF</button>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {selected && dashboard && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">📊 Dashboard: {selected.name}</span>
            <button className="ghost sm" onClick={() => { setSelected(null); setDashboard(null); }}>✕ Đóng</button>
          </div>
          <div className="grid-4" style={{ marginBottom: 16 }}>
            {[
              { label: 'Học sinh', value: dashboard.total_students ?? dashboard.students?.length ?? 0, color: '' },
              { label: 'Điểm TB đầu vào', value: (dashboard.avg_entry_score ?? 0).toFixed(1), color: 'green' },
              { label: 'Đã hoàn thành', value: dashboard.completed_students ?? 0, color: 'green' },
              { label: 'Đang học', value: dashboard.active_students ?? 0, color: 'orange' },
            ].map((s, i) => (
              <div key={i} className={`stat-card ${s.color}`}>
                <div className="stat-label">{s.label}</div>
                <div className="stat-value">{s.value}</div>
              </div>
            ))}
          </div>
          {dashboard.students?.length > 0 && (
            <div className="table-wrap">
              <table className="results-table">
                <thead><tr><th>Học sinh</th><th>Điểm đầu vào</th><th>Trình độ</th><th>Tiến độ</th></tr></thead>
                <tbody>
                  {dashboard.students.map((s, i) => (
                    <tr key={i}>
                      <td>{s.name || s.student_name || `Học sinh ${s.student_id}`}</td>
                      <td>{s.entry_score ?? s.score ?? 'N/A'}</td>
                      <td><span className={`badge ${levelClass(s.level)}`}>{levelVN(s.level)}</span></td>
                      <td>
                        <div className="progress-bar" style={{ width: 80 }}>
                          <div className="progress-fill" style={{ width: `${s.progress ?? 0}%` }} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function TabResults({ setAlert }) {
  const [loading, setLoading] = React.useState(false);
  const [results, setResults] = React.useState([]);
  const [page, setPage] = React.useState(1);
  const [total, setTotal] = React.useState(0);
  const pageSize = 15;

  const load = React.useCallback(async (p) => {
    setLoading(true);
    try {
      const res = await mvpApi.getResults(p, pageSize);
      const d = res.data.data;
      setResults(d.items || []);
      setTotal(d.pagination?.total || 0);
      setPage(d.pagination?.page || p);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => { load(1); }, [load]);

  return (
    <div className="stack">
      <div className="row-between">
        <h2 style={{ fontSize: 18 }}>📋 Kết quả kiểm tra học sinh</h2>
        <span className="badge gray">{total} kết quả</span>
      </div>
      {loading ? <LoadingSpinner label="Đang tải..." /> : (
        results.length === 0 ? (
          <div className="empty-state"><div className="empty-icon">📋</div><p>Chưa có kết quả nào.</p></div>
        ) : (
          <div className="table-wrap">
            <table className="results-table">
              <thead>
                <tr><th>#</th><th>Học sinh</th><th>Điểm</th><th>Trình độ</th><th>Thời gian</th></tr>
              </thead>
              <tbody>
                {results.map((r, i) => (
                  <tr key={r.result_id || i}>
                    <td>{(page - 1) * pageSize + i + 1}</td>
                    <td>{r.student_name || `ID: ${r.student_id}`}</td>
                    <td><strong style={{ color: r.score >= 7 ? 'var(--success)' : r.score >= 5 ? 'var(--warning)' : 'var(--danger)' }}>{r.score}/10</strong></td>
                    <td><span className={`badge ${levelClass(r.level)}`}>{levelVN(r.level)}</span></td>
                    <td style={{ color: 'var(--gray-400)', fontSize: 13 }}>{r.submitted_at ? new Date(r.submitted_at).toLocaleString('vi-VN') : 'N/A'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
      <div className="pagination">
        <button className="ghost sm" disabled={page <= 1} onClick={() => load(page - 1)}>← Trước</button>
        <span>Trang {page} / {Math.ceil(total / pageSize) || 1}</span>
        <button className="ghost sm" disabled={page * pageSize >= total} onClick={() => load(page + 1)}>Sau →</button>
      </div>
    </div>
  );
}

function TabAnalytics() {
  const [loading, setLoading] = React.useState(false);
  const [results, setResults] = React.useState([]);

  React.useEffect(() => {
    const fetchAll = async () => {
      setLoading(true);
      try {
        const res = await mvpApi.getResults(1, 100);
        const items = res.data.data?.items || [];
        setResults(items);
      } catch {
        setResults([]);
      }
      setLoading(false);
    };
    fetchAll();
  }, []);

  const levelDist = React.useMemo(() => {
    const counts = { 'Cơ bản': 0, 'Trung bình': 0, 'Nâng cao': 0 };
    results.forEach((r) => { counts[levelVN(r.level)] = (counts[levelVN(r.level)] || 0) + 1; });
    return Object.entries(counts).map(([name, value]) => ({ name, value }));
  }, [results]);

  const scoreData = React.useMemo(() => {
    const groups = {};
    results.forEach((r) => {
      const d = r.submitted_at ? new Date(r.submitted_at).toLocaleDateString('vi-VN') : 'N/A';
      if (!groups[d]) groups[d] = { date: d, scores: [] };
      groups[d].scores.push(Number(r.score) || 0);
    });
    return Object.values(groups).slice(-14).map((g) => ({
      date: g.date,
      avg: +(g.scores.reduce((a, b) => a + b, 0) / g.scores.length).toFixed(1),
      count: g.scores.length,
    }));
  }, [results]);

  if (loading) return <LoadingSpinner label="Đang tải phân tích..." />;

  const avg = results.length ? (results.reduce((a, r) => a + (Number(r.score) || 0), 0) / results.length).toFixed(1) : 0;
  const pass = results.filter((r) => (Number(r.score) || 0) >= 5).length;

  return (
    <div className="stack">
      <h2 style={{ fontSize: 18 }}>📊 Thống kê & Phân tích</h2>

      <div className="grid-4">
        {[
          { label: 'Tổng lượt thi', value: results.length, color: '' },
          { label: 'Điểm trung bình', value: avg, color: 'green' },
          { label: 'Tỉ lệ đạt (≥5)', value: results.length ? `${Math.round((pass / results.length) * 100)}%` : '–', color: 'green' },
          { label: 'Cần hỗ trợ (<5)', value: results.length - pass, color: 'red' },
        ].map((s, i) => (
          <div key={i} className={`stat-card ${s.color}`}>
            <div className="stat-label">{s.label}</div>
            <div className="stat-value">{s.value}</div>
          </div>
        ))}
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-title" style={{ marginBottom: 12 }}>📈 Điểm trung bình theo ngày</div>
          {scoreData.length > 0 ? (
            <div className="chart-container">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={scoreData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis domain={[0, 10]} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Line type="monotone" dataKey="avg" stroke="#4f46e5" strokeWidth={2} dot={{ fill: '#4f46e5' }} name="Điểm TB" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : <div className="empty-state" style={{ padding: 24 }}><p>Chưa có dữ liệu</p></div>}
        </div>

        <div className="card">
          <div className="card-title" style={{ marginBottom: 12 }}>🥧 Phân loại trình độ</div>
          {levelDist.some((d) => d.value > 0) ? (
            <div className="chart-container">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={levelDist} cx="50%" cy="50%" outerRadius={90} dataKey="value" label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                    {levelDist.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Legend />
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : <div className="empty-state" style={{ padding: 24 }}><p>Chưa có dữ liệu</p></div>}
        </div>
      </div>

      {results.length > 0 && (
        <div className="card">
          <div className="card-title" style={{ marginBottom: 12 }}>📊 Phân bố điểm số</div>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((score) => ({
                score: `${score}`,
                count: results.filter((r) => Math.floor(Number(r.score) || 0) === score).length,
              }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="score" label={{ value: 'Điểm', position: 'insideBottom', offset: -2 }} />
                <YAxis />
                <Tooltip />
                <Bar dataKey="count" fill="#4f46e5" name="Số học sinh" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}

function TabExamGen({ setAlert }) {
  const [loading, setLoading] = React.useState(false);
  const [form, setForm] = React.useState({ courseId: '', numVariants: 2, numQuestions: 10, examType: 'multiple_choice' });
  const [batchId, setBatchId] = React.useState(null);
  const upd = (k, v) => setForm((p) => ({ ...p, [k]: v }));

  const generate = async () => {
    if (!form.numVariants || !form.numQuestions) return;
    setLoading(true);
    try {
      const res = await mvpApi.generateExamDocx(
        form.courseId || null,
        Number(form.numVariants),
        Number(form.numQuestions),
        form.examType,
      );
      if (res.data instanceof Blob) {
        downloadBlob(res.data, 'de-thi.zip');
        setAlert({ type: 'success', message: '✅ Đã tải xuống đề thi!' });
      } else {
        const id = res.data?.batch_id || res.data?.data?.batch_id;
        if (id) {
          setBatchId(id);
          setAlert({ type: 'success', message: `✅ Đã sinh ${form.numVariants} đề thi. Nhấn Tải về để lấy file.` });
        } else {
          setAlert({ type: 'success', message: '✅ Đề thi đã được sinh. Kiểm tra kết quả.' });
        }
      }
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  const downloadZip = async () => {
    if (!batchId) return;
    setLoading(true);
    try {
      const res = await mvpApi.exportExamVariantsZip(batchId);
      downloadBlob(res.data, `de-thi-${batchId}.zip`);
      setAlert({ type: 'success', message: '✅ Đã tải file ZIP chứa đề thi Word.' });
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="stack">
      <h2 style={{ fontSize: 18 }}>📝 Sinh đề thi tự động</h2>
      <div className="card">
        <div className="card-title" style={{ marginBottom: 16 }}>⚙️ Cấu hình đề thi</div>
        <div className="grid-2" style={{ gap: 14 }}>
          <div className="form-group">
            <label>Số đề cần sinh</label>
            <input type="number" min={1} max={10} value={form.numVariants} onChange={(e) => upd('numVariants', e.target.value)} />
            <small>Tối đa 10 đề khác nhau</small>
          </div>
          <div className="form-group">
            <label>Số câu mỗi đề</label>
            <input type="number" min={5} max={50} value={form.numQuestions} onChange={(e) => upd('numQuestions', e.target.value)} />
            <small>Từ 5 đến 50 câu</small>
          </div>
          <div className="form-group">
            <label>Hình thức</label>
            <select value={form.examType} onChange={(e) => upd('examType', e.target.value)}>
              <option value="multiple_choice">Trắc nghiệm</option>
              <option value="essay">Tự luận</option>
              <option value="mixed">Kết hợp</option>
            </select>
          </div>
          <div className="form-group">
            <label>Phân bố độ khó</label>
            <select defaultValue="balanced">
              <option value="balanced">Cân bằng (3 mức)</option>
              <option value="easy_heavy">Nhiều câu dễ</option>
              <option value="hard_heavy">Nhiều câu khó</option>
            </select>
          </div>
        </div>
        <div className="alert info" style={{ marginTop: 12 }}>
          💡 Đề thi sẽ bao gồm 3 mức độ: <strong>Dễ · Trung bình · Khó</strong>. File xuất ra định dạng <strong>Word (.docx)</strong> có thể in ngay.
        </div>
        <div className="row" style={{ marginTop: 16 }}>
          <button disabled={loading} onClick={generate}>
            {loading ? '⏳ Đang sinh đề...' : `📝 Sinh ${form.numVariants} đề thi`}
          </button>
          {batchId && (
            <button className="success-btn" onClick={downloadZip} disabled={loading}>
              📥 Tải về file Word (.zip)
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

const TABS = [
  { key: 'upload', label: '📄 Tải tài liệu', icon: '📄' },
  { key: 'classrooms', label: '🏫 Quản lý lớp', icon: '🏫' },
  { key: 'results', label: '📋 Kết quả', icon: '📋' },
  { key: 'analytics', label: '📊 Thống kê', icon: '📊' },
  { key: 'examgen', label: '📝 Sinh đề Word', icon: '📝' },
];

export default function TeacherDashboard() {
  const { user } = useAuth();
  const [tab, setTab] = React.useState('upload');
  const [alert, setAlert] = React.useState({ type: 'info', message: '' });

  const clearAlert = () => setAlert({ type: 'info', message: '' });

  return (
    <div className="shell">
      <div className="page-header">
        <div className="row-between">
          <div>
            <h1>👩‍🏫 Bảng điều khiển Giáo viên</h1>
            <p>Xin chào, <strong>{user?.full_name || user?.email}</strong> · Quản lý lớp học và tài liệu</p>
          </div>
        </div>
      </div>

      {alert.message && (
        <div style={{ marginBottom: 16 }}>
          <Alert type={alert.type} message={alert.message} />
        </div>
      )}

      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.key} className={`tab ${tab === t.key ? 'active' : ''}`} onClick={() => { setTab(t.key); clearAlert(); }}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'upload' && <TabUpload setAlert={setAlert} />}
      {tab === 'classrooms' && <TabClassrooms setAlert={setAlert} />}
      {tab === 'results' && <TabResults setAlert={setAlert} />}
      {tab === 'analytics' && <TabAnalytics />}
      {tab === 'examgen' && <TabExamGen setAlert={setAlert} />}
    </div>
  );
}
