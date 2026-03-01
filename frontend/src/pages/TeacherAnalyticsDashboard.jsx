import { useEffect, useMemo, useState } from 'react';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from 'recharts';
import { apiJson, API_BASE, buildAuthHeaders } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import Card from '../ui/Card';
import Button from '../ui/Button';
import PageHeader from '../ui/PageHeader';
import EmptyState from '../ui/EmptyState';

export default function TeacherAnalyticsDashboard() {
  const { role, userId } = useAuth();
  const [classroomId, setClassroomId] = useState(localStorage.getItem('teacher_report_classroom_id') || '1');
  const [report, setReport] = useState(null);
  const [hoursData, setHoursData] = useState([]);
  const [loading, setLoading] = useState(false);

  const loadReport = async () => {
    const cid = Number(classroomId || 0);
    if (!cid) return;
    setLoading(true);
    try {
      localStorage.setItem('teacher_report_classroom_id', String(cid));
      const data = await apiJson(`/lms/teacher/report/${cid}`);
      setReport(data);
      if (userId) {
        const hours = await apiJson(`/analytics/learning-hours?user_id=${Number(userId)}&days=30`);
        setHoursData(Array.isArray(hours) ? hours : []);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (role === 'teacher') loadReport();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role]);

  const rows = useMemo(() => (Array.isArray(report?.per_student) ? report.per_student : []), [report]);

  const download = async (url, filename) => {
    const res = await fetch(url, { headers: buildAuthHeaders() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  if (role !== 'teacher') {
    return <div className='container'><Card><p className='page-subtitle'>Trang này dành cho giáo viên.</p></Card></div>;
  }

  return (
    <div className='container grid-12'>
      <Card className='span-12'>
        <PageHeader title='Phân tích học tập' subtitle='Theo dõi báo cáo lớp, tải PDF/Excel và xem tiến độ theo thời gian.' breadcrumbs={['Giáo viên', 'Phân tích học tập']} />
      </Card>

      <Card className='span-12 stack-md'>
        <div className='row'>
          <input className='input' value={classroomId} onChange={(e) => setClassroomId(e.target.value)} style={{ maxWidth: 160 }} aria-label='Mã lớp học' />
          <Button onClick={loadReport}>{loading ? 'Đang tải...' : 'Tải báo cáo'}</Button>
          <Button onClick={() => download(`${API_BASE}/lms/teacher/report/${Number(classroomId)}/export/pdf`, `teacher_report_${classroomId}.pdf`)}>Xuất báo cáo PDF</Button>
          <Button onClick={() => download(`${API_BASE}/lms/teacher/report/${Number(classroomId)}/export/excel`, `teacher_report_${classroomId}.xlsx`)}>Xuất Excel</Button>
        </div>

        <div className='grid-12'>
          <Card className='span-4'>Tổng học viên: <b>{report?.summary?.total_students || 0}</b></Card>
          <Card className='span-4'>Đã có điểm cuối kỳ: <b>{report?.summary?.students_with_final || 0}</b></Card>
        </div>

        <Card className='stack-sm'>
          <h3 className='section-title'>Biểu đồ giờ học theo ngày (30 ngày)</h3>
          <div style={{ width: '100%', height: 280 }}>
            <ResponsiveContainer>
              <LineChart data={hoursData}>
                <CartesianGrid strokeDasharray='3 3' stroke='var(--border)' />
                <XAxis dataKey='date' stroke='var(--muted)' />
                <YAxis stroke='var(--muted)' />
                <Tooltip />
                <Line type='monotone' dataKey='hours' stroke='var(--primary)' strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {!rows.length ? (
          <EmptyState icon='📊' title='Chưa có dữ liệu học viên' description='Hãy tải báo cáo của lớp học khác hoặc thử lại sau.' />
        ) : (
          <div className='data-table-wrap'>
            <table className='data-table'>
              <thead><tr><th>Tên học viên</th><th>Điểm đầu vào</th><th>Điểm cuối kỳ</th><th>Cải thiện</th></tr></thead>
              <tbody>
                {rows.map((s) => (
                  <tr key={s.student_id}>
                    <td>{s.student_name || s.name}</td><td>{s.placement_score ?? '—'}</td><td>{s.final_score ?? '—'}</td><td>{s.improvement ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
