import React from 'react';
import Alert from '../components/Alert';
import { useAuth } from '../auth';
import TeacherUpload from '../components/teacher/TeacherUpload';
import TeacherClassSetup from '../components/teacher/TeacherClassSetup';
import TeacherAssessments from '../components/teacher/TeacherAssessments';
import TeacherMonitor from '../components/teacher/TeacherMonitor';
import TeacherReports from '../components/teacher/TeacherReports';
import ExamExportModal from '../components/ExamExportModal';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
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
      setClassrooms(res.data.data?.items || res.data.data || res.data.classrooms || []);
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
  const [analytics, setAnalytics] = React.useState(null);
  const [classroomId, setClassroomId] = React.useState(null);

  React.useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const clsRes = await mvpApi.getMyClassrooms();
        const classes = clsRes?.data?.data || [];
        if (!classes.length) {
          setAnalytics(null);
          return;
        }
        const selectedId = classes[0].id;
        setClassroomId(selectedId);
        const res = await mvpApi.getTeacherClassroomAnalytics(selectedId);
        setAnalytics(res.data || null);
      } catch {
        setAnalytics(null);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const exportReport = async (fmt) => {
    if (!classroomId) return;
    const res = await mvpApi.exportTeacherReport(classroomId, fmt);
    downloadBlob(res.data, `teacher_report_${classroomId}.${fmt}`);
  };

  const levelDist = React.useMemo(() => {
    const base = analytics?.level_distribution || { beginner: 0, intermediate: 0, advanced: 0 };
    const total = Math.max(1, Object.values(base).reduce((a, b) => a + Number(b || 0), 0));
    return [
      { name: 'Beginner', value: Number(base.beginner || 0), percent: Math.round((Number(base.beginner || 0) / total) * 100) },
      { name: 'Intermediate', value: Number(base.intermediate || 0), percent: Math.round((Number(base.intermediate || 0) / total) * 100) },
      { name: 'Advanced', value: Number(base.advanced || 0), percent: Math.round((Number(base.advanced || 0) / total) * 100) },
    ];
  }, [analytics]);

  const scoreDistribution = React.useMemo(() => {
    return (analytics?.score_distribution || []).map((item) => ({
      ...item,
      fill: (item.range === '0-20' || item.range === '21-40' || item.range === '41-60') ? '#ef4444' : '#10b981',
    }));
  }, [analytics]);

  const kpis = {
    totalStudents: Number(analytics?.total_students || 0),
    avgScore: Number(analytics?.avg_score || 0),
    completionRate: Number(analytics?.completion_rate || 0),
    supportNeeded: Number(analytics?.support_needed || 0),
  };

  if (loading) return <LoadingSpinner label="Đang tải phân tích lớp học..." />;

  if (!analytics) {
    return (
      <div className="empty-state">
        <div className="empty-icon">📊</div>
        <p>Chưa có dữ liệu analytics cho lớp học.</p>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="row-between">
        <h2 className="section-title">📊 Teacher Dashboard</h2>
        <div className="row">
          <button className="ghost sm" onClick={() => exportReport('pdf')} disabled={!classroomId}>📄 Xuất PDF</button>
          <button className="ghost sm" onClick={() => exportReport('xlsx')} disabled={!classroomId}>📊 Xuất Excel</button>
        </div>
      </div>

      <div className="grid-4">
        <div className="stat-card"><div className="stat-label">Tổng số học sinh</div><div className="stat-value">{kpis.totalStudents}</div></div>
        <div className="stat-card green"><div className="stat-label">Điểm trung bình lớp</div><div className="stat-value">{kpis.avgScore.toFixed(1)}%</div></div>
        <div className="stat-card orange"><div className="stat-label">Tỷ lệ hoàn thành</div><div className="stat-value">{kpis.completionRate.toFixed(1)}%</div></div>
        <div className="stat-card red"><div className="stat-label">Cần hỗ trợ (&lt;50%)</div><div className="stat-value">{kpis.supportNeeded}</div></div>
      </div>

      <div className="grid-2">
        <div className="card"><div className="card-title">1) ScoreDistributionChart</div><div className="chart-container"><ResponsiveContainer width="100%" height="100%"><BarChart data={scoreDistribution}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="range" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="count">{scoreDistribution.map((entry) => <Cell key={entry.range} fill={entry.fill} />)}</Bar></BarChart></ResponsiveContainer></div></div>
        <div className="card"><div className="card-title">2) LevelPieChart</div><div className="chart-container"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={levelDist} dataKey="value" nameKey="name" outerRadius={85} label={({ name, percent }) => `${name}: ${percent}%`}>{levelDist.map((entry, i) => <Cell key={entry.name} fill={["#ef4444", "#f59e0b", "#10b981"][i]} />)}</Pie><Legend formatter={(v, _e, idx) => `${v} (${levelDist[idx]?.value || 0})`} /><Tooltip /></PieChart></ResponsiveContainer></div></div>
      </div>

      <div className="grid-2">
        <div className="card"><div className="card-title">3) StudyTimeChart - 7 ngày gần nhất</div><div className="chart-container"><ResponsiveContainer width="100%" height="100%"><LineChart data={analytics?.study_time_weekly || []}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" /><YAxis /><Tooltip /><Line type="monotone" dataKey="hours" stroke="#4f46e5" strokeWidth={2} /></LineChart></ResponsiveContainer></div></div>
        <div className="card"><div className="card-title">4) TopicMasteryChart</div><div className="chart-container"><ResponsiveContainer width="100%" height="100%"><RadarChart data={analytics?.topic_mastery || []}><PolarGrid /><PolarAngleAxis dataKey="topic" /><PolarRadiusAxis domain={[0, 100]} /><Radar name="Avg Score" dataKey="avg_score" stroke="#4f46e5" fill="#4f46e5" fillOpacity={0.3} /><Tooltip /></RadarChart></ResponsiveContainer></div></div>
      </div>

      <div className="card">
        <div className="card-title">5) ProgressComparisonChart (Placement vs Final)</div>
        <div className="chart-container"><ResponsiveContainer width="100%" height="100%"><LineChart data={analytics?.progress_comparison || []}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="student_name" /><YAxis domain={[0, 100]} /><Tooltip /><Legend /><Line type="monotone" dataKey="placement" stroke="#f59e0b" /><Line type="monotone" dataKey="final" stroke="#10b981" /></LineChart></ResponsiveContainer></div>
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
  { key: 'upload', label: 'B1 · Upload PDF' },
  { key: 'class', label: 'B2 · Tạo lớp học' },
  { key: 'assessments', label: 'B3 · Cấu hình bài kiểm tra' },
  { key: 'monitor', label: 'B4 · Monitor & report' },
  { key: 'reports', label: 'B5 · Xuất báo cáo' },
];

const initialWorkflow = {
  courseId: null,
  uploadReady: false,
  topicsDraft: [],
  selectedTopicIds: [],
  uploadedDocuments: [],
  topicsPublished: false,
  classroomId: null,
  inviteCode: '',
  assessmentActivated: false,
  assessmentId: null,
};

export default function TeacherDashboard() {
  const { user } = useAuth();
  const [tab, setTab] = React.useState('upload');
  const [alert, setAlert] = React.useState({ type: 'info', message: '' });
  const [workflow, setWorkflow] = React.useState(initialWorkflow);

  const gotoTab = (nextTab) => {
    if (nextTab) setTab(nextTab);
    setAlert({ type: 'info', message: '' });
  };

  return (
    <div className="shell">
      <div className="page-header">
        <h1>👩‍🏫 Teacher Workflow</h1>
        <p>Xin chào, <strong>{user?.full_name || user?.email}</strong> · Điều phối toàn bộ quy trình dạy học từ upload tài liệu đến xuất báo cáo.</p>
      </div>

      {alert.message && <Alert type={alert.type} message={alert.message} />}

      <div className="tabs">
        {TABS.map((item) => (
          <button key={item.key} className={`tab ${tab === item.key ? 'active' : ''}`} onClick={() => gotoTab(item.key)}>
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'upload' && (
        <TeacherUpload
          setAlert={setAlert}
          workflow={workflow}
          setWorkflow={setWorkflow}
          onContinue={gotoTab}
        />
      )}
      {tab === 'class' && (
        <TeacherClassSetup
          setAlert={setAlert}
          workflow={workflow}
          setWorkflow={setWorkflow}
          onContinue={gotoTab}
        />
      )}
      {tab === 'assessments' && (
        <TeacherAssessments
          setAlert={setAlert}
          workflow={workflow}
          setWorkflow={setWorkflow}
        />
      )}
      {tab === 'monitor' && <TeacherMonitor setAlert={setAlert} workflow={workflow} />}
      {tab === 'reports' && <TeacherReports setAlert={setAlert} workflow={workflow} />}
    </div>
  );
}
