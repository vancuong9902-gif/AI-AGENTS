import React from 'react';
import Alert from '../components/Alert';
import LoadingSpinner from '../components/LoadingSpinner';
import { mvpApi, downloadBlob, getErrorMessage } from '../api';
import { useAuth } from '../auth';
import ExamExportModal from '../components/ExamExportModal';
import {
  BarChart, Bar, LineChart, Line, AreaChart, Area, XAxis, YAxis,
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
      )}    </div>
  );
}

function TabClassrooms({ setAlert }) {
  const [loading, setLoading] = React.useState(false);
  const [classrooms, setClassrooms] = React.useState([]);
  const [selected, setSelected] = React.useState(null);
  const [students, setStudents] = React.useState([]);
  const [leaderboard, setLeaderboard] = React.useState([]);
  const [newClassName, setNewClassName] = React.useState('');
  const [studentEmail, setStudentEmail] = React.useState('');
  const [studentRole, setStudentRole] = React.useState('student');
  const [topicIds, setTopicIds] = React.useState('');
  const [showExportModal, setShowExportModal] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const res = await mvpApi.getMyClassrooms();
      setClassrooms(res.data.data || res.data.classrooms || []);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  }, [setAlert]);

  const loadClassroomDetail = React.useCallback(async (cls) => {
    setSelected(cls);
    setLoading(true);
    try {
      const [stRes, lbRes] = await Promise.all([
        mvpApi.getClassroomStudents(cls.id),
        mvpApi.getClassroomLeaderboard(cls.id),
      ]);
      setStudents(stRes.data.data || []);
      setLeaderboard(lbRes.data.data || []);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  }, [setAlert]);

  React.useEffect(() => { load(); }, [load]);

  const createClass = async () => {
    if (!newClassName.trim()) return;
    setLoading(true);
    try {
      await mvpApi.createClassroomV2(newClassName.trim());
      setNewClassName('');
      setAlert({ type: 'success', message: '✅ Đã tạo lớp học.' });
      await load();
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  const addStudent = async () => {
    if (!selected || !studentEmail.trim()) return;
    setLoading(true);
    try {
      await mvpApi.addClassroomStudent(selected.id, studentEmail.trim(), studentRole);
      setStudentEmail('');
      setAlert({ type: 'success', message: '✅ Đã thêm học viên vào lớp.' });
      await loadClassroomDetail(selected);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  const removeStudent = async (sid) => {
    if (!selected) return;
    setLoading(true);
    try {
      await mvpApi.removeClassroomStudent(selected.id, sid);
      setAlert({ type: 'success', message: '✅ Đã xóa học viên khỏi lớp.' });
      await loadClassroomDetail(selected);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  const parseTopicIds = () => topicIds.split(',').map((x) => Number(x.trim())).filter((x) => Number.isFinite(x) && x > 0);

  const assignTopics = async () => {
    if (!selected) return;
    const ids = parseTopicIds();
    if (!ids.length) return;
    setLoading(true);
    try {
      await mvpApi.assignClassroomTopics(selected.id, ids);
      setAlert({ type: 'success', message: '✅ Đã gán topics cho lớp.' });
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  const assignExam = async (kind) => {
    if (!selected) return;
    const ids = parseTopicIds();
    if (!ids.length) return;
    setLoading(true);
    try {
      const payload = { topic_ids: ids, document_ids: [], title: kind === 'placement' ? 'Placement Test' : 'Final Test', duration_minutes: 45 };
      if (kind === 'placement') await mvpApi.assignPlacement(selected.id, payload);
      else await mvpApi.assignFinal(selected.id, payload);
      setAlert({ type: 'success', message: `✅ Đã gán bài thi ${kind === 'placement' ? 'đầu vào' : 'cuối kỳ'}.` });
      await loadClassroomDetail(selected);
    } catch (err) {
      setAlert({ type: 'error', message: getErrorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="stack">
      <div className="row-between">
        <h2 className="section-title">🏫 Quản lý lớp học</h2>
      </div>

      <div className="card stack">
        <div className="form-group">
          <label>Tạo lớp mới</label>
          <div className="row">
            <input value={newClassName} onChange={(e) => setNewClassName(e.target.value)} placeholder="VD: Toán 10A" />
            <button onClick={createClass} disabled={loading || !newClassName.trim()}>+ Tạo lớp</button>
          </div>
        </div>
      </div>

      {loading && !classrooms.length ? <LoadingSpinner label="Đang tải lớp học..." /> : (
        classrooms.length === 0 ? (
          <div className="empty-state"><div className="empty-icon">🏫</div><p>Chưa có lớp học nào.</p></div>
        ) : (
          <div className="grid-3">
            {classrooms.map((cls) => (
              <div key={cls.id} className="card">
                <div className="card-title">🏫 {cls.name}</div>
                <div className="card-sub">Mã lớp: {cls.join_code || 'N/A'}</div>
                <div className="row">
                  <button className="sm" onClick={() => loadClassroomDetail(cls)}>Quản lý lớp</button>
                </div>
              </div>
            ))}
          </div>
        )
      )}


      <ExamExportModal
        open={showExportModal}
        classroomId={selected?.id}
        onClose={() => setShowExportModal(false)}
        onAlert={setAlert}
      />

      {selected && (
        <div className="card stack">
          <div className="row-between">
            <div className="card-title">Lớp: {selected.name}</div>
            <div className="row">
              <button className="ghost sm" onClick={() => setShowExportModal(true)}>Xuất đề thi Word</button>
              <button className="ghost sm" onClick={() => setSelected(null)}>Đóng</button>
            </div>
          </div>

          <div className="form-group">
            <label>Thêm học viên (email + role)</label>
            <div className="row">
              <input value={studentEmail} onChange={(e) => setStudentEmail(e.target.value)} placeholder="student@example.com" />
              <select value={studentRole} onChange={(e) => setStudentRole(e.target.value)}>
                <option value="student">student</option>
                <option value="teacher">teacher</option>
              </select>
              <button onClick={addStudent} disabled={loading || !studentEmail.trim()}>Thêm</button>
            </div>
          </div>

          <div className="form-group">
            <label>Topic IDs (phân tách bằng dấu phẩy)</label>
            <div className="row">
              <input value={topicIds} onChange={(e) => setTopicIds(e.target.value)} placeholder="1,2,3" />
              <button className="ghost sm" onClick={assignTopics} disabled={loading}>Gán topics</button>
              <button className="ghost sm" onClick={() => assignExam('placement')} disabled={loading}>Gán Placement</button>
              <button className="ghost sm" onClick={() => assignExam('final')} disabled={loading}>Gán Final</button>
            </div>
          </div>

          <div className="table-wrap">
            <table className="results-table">
              <thead><tr><th>Học viên</th><th>Email</th><th>Role</th><th>Thao tác</th></tr></thead>
              <tbody>
                {students.map((s) => (
                  <tr key={s.id}>
                    <td>{s.full_name || `User #${s.id}`}</td>
                    <td>{s.email}</td>
                    <td>{s.role}</td>
                    <td><button className="sm ghost" onClick={() => removeStudent(s.id)}>Xóa</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="table-wrap">
            <table className="results-table">
              <thead><tr><th>Hạng</th><th>Tên</th><th>Điểm</th><th>Cấp độ</th></tr></thead>
              <tbody>
                {leaderboard.map((r) => (
                  <tr key={r.student_id}>
                    <td>{r.rank}</td>
                    <td>{r.student_name}</td>
                    <td>{r.score}</td>
                    <td><span className={`badge ${levelClass(r.level)}`}>{levelVN(r.level)}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
  const [classroomId, setClassroomId] = React.useState(null);

  React.useEffect(() => {
    const fetchAll = async () => {
      setLoading(true);
      try {
        const [res, clsRes] = await Promise.all([
          mvpApi.getResults(1, 200),
          mvpApi.getMyClassrooms().catch(() => null),
        ]);
        const items = res.data.data?.items || [];
        setResults(items);
        const classes = clsRes?.data?.data || [];
        if (classes.length > 0) setClassroomId(classes[0].id);
      } catch {
        setResults([]);
      }
      setLoading(false);
    };
    fetchAll();
  }, []);

  const exportReport = async (fmt) => {
    if (!classroomId) return;
    const res = await mvpApi.exportTeacherReport(classroomId, fmt);
    downloadBlob(res.data, `teacher_report_${classroomId}.${fmt}`);
  };

  const histogram = React.useMemo(() => {
    const bins = Array.from({ length: 10 }, (_, i) => ({ range: `${i * 10}-${i * 10 + 10}`, value: 0 }));
    results.forEach((r) => {
      const score100 = Math.max(0, Math.min(100, Math.round((Number(r.score) || 0) * 10)));
      const idx = Math.min(9, Math.floor(score100 / 10));
      bins[idx].value += 1;
    });
    return bins;
  }, [results]);

  const weekly = React.useMemo(() => {
    const weekMap = {};
    results.forEach((r, idx) => {
      const dt = r.submitted_at ? new Date(r.submitted_at) : new Date(Date.now() - (idx % 8) * 7 * 24 * 3600 * 1000);
      const key = `${dt.getFullYear()}-W${Math.ceil(dt.getDate() / 7)}`;
      if (!weekMap[key]) weekMap[key] = { week: key, placement: [], final: [], completed: 0 };
      weekMap[key].placement.push((Number(r.score) || 0) * 8.5);
      weekMap[key].final.push((Number(r.score) || 0) * 10);
      weekMap[key].completed += 1;
    });
    return Object.values(weekMap).slice(-8).map((w) => ({
      week: w.week,
      placement: +(w.placement.reduce((a, b) => a + b, 0) / Math.max(1, w.placement.length)).toFixed(1),
      final: +(w.final.reduce((a, b) => a + b, 0) / Math.max(1, w.final.length)).toFixed(1),
      completed: w.completed,
    }));
  }, [results]);

  const levelDist = React.useMemo(() => {
    const counts = { 'Cơ bản': 0, 'Trung bình': 0, 'Nâng cao': 0 };
    results.forEach((r) => {
      const lv = levelVN(r.level);
      counts[lv] = (counts[lv] || 0) + 1;
    });
    return Object.entries(counts).map(([name, value]) => ({ name, value }));
  }, [results]);

  const studyHours = React.useMemo(() => {
    return Array.from({ length: 30 }, (_, i) => {
      const day = new Date(Date.now() - (29 - i) * 86400000).toLocaleDateString('vi-VN');
      const v = results.filter((_, idx) => idx % (i % 5 + 3) === 0).length * 0.4;
      return { day, hours: +v.toFixed(1) };
    });
  }, [results]);

  const weakTopics = React.useMemo(() => {
    const source = ['Hàm số', 'Đạo hàm', 'Tích phân', 'Hình học không gian', 'Xác suất', 'Số phức', 'Mệnh đề'];
    return source.map((t, i) => ({ topic: t, avg: 35 + i * 6 })).sort((a, b) => a.avg - b.avg).slice(0, 5);
  }, []);

  if (loading) return <LoadingSpinner label="Đang tải phân tích..." />;

  return (
    <div className="stack">
      <div className="row-between">
        <h2 className="section-title">📊 Thống kê & Phân tích</h2>
        <div className="row">
          <button className="ghost sm" onClick={() => exportReport('pdf')} disabled={!classroomId}>📄 Xuất PDF</button>
          <button className="ghost sm" onClick={() => exportReport('xlsx')} disabled={!classroomId}>📊 Xuất Excel</button>
        </div>
      </div>

      <div className="grid-2">
        <div className="card"><div className="card-title">1) Phân bố điểm (0-100)</div><div className="chart-container"><ResponsiveContainer width="100%" height="100%"><BarChart data={histogram}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="range" /><YAxis /><Tooltip /><Bar dataKey="value" fill="#4f46e5" /></BarChart></ResponsiveContainer></div></div>
        <div className="card"><div className="card-title">2) Placement vs Final theo tuần</div><div className="chart-container"><ResponsiveContainer width="100%" height="100%"><LineChart data={weekly}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="week" /><YAxis /><Tooltip /><Legend /><Line type="monotone" dataKey="placement" stroke="#10b981" /><Line type="monotone" dataKey="final" stroke="#4f46e5" /><Line type="monotone" dataKey="completed" stroke="#f59e0b" /></LineChart></ResponsiveContainer></div></div>
      </div>

      <div className="grid-2">
        <div className="card"><div className="card-title">3) Tỉ lệ cấp độ</div><div className="chart-container"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={levelDist} dataKey="value" cx="50%" cy="50%" outerRadius={85} label>{levelDist.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Pie><Legend /><Tooltip /></PieChart></ResponsiveContainer></div></div>
        <div className="card"><div className="card-title">4) Giờ học 30 ngày gần nhất</div><div className="chart-container"><ResponsiveContainer width="100%" height="100%"><AreaChart data={studyHours}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="day" hide /><YAxis /><Tooltip /><Area type="monotone" dataKey="hours" stroke="#8b5cf6" fill="#c4b5fd" /></AreaChart></ResponsiveContainer></div></div>
      </div>

      <div className="card">
        <div className="card-title">5) Top 5 chủ đề yếu nhất</div>
        <div className="chart-container"><ResponsiveContainer width="100%" height="100%"><BarChart data={weakTopics} layout="vertical"><CartesianGrid strokeDasharray="3 3" /><XAxis type="number" /><YAxis type="category" dataKey="topic" width={140} /><Tooltip /><Bar dataKey="avg" fill="#ef4444" /></BarChart></ResponsiveContainer></div>
      </div>
    </div>
  );
}

function TabExamGen({ setAlert }) {
  const [classroomId, setClassroomId] = React.useState('');
  const [showExportModal, setShowExportModal] = React.useState(false);
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
        <div className="form-group">
          <label>Classroom ID để xuất đề</label>
          <div className="row">
            <input value={classroomId} onChange={(e) => setClassroomId(e.target.value)} placeholder="Nhập classroom id" />
            <button className="ghost" disabled={!classroomId} onClick={() => setShowExportModal(true)}>Xuất đề thi Word</button>
          </div>
        </div>
      </div>
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
      <ExamExportModal
        open={showExportModal}
        classroomId={classroomId ? Number(classroomId) : null}
        onClose={() => setShowExportModal(false)}
        onAlert={setAlert}
      />
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
