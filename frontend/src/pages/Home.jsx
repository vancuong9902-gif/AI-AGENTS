import { Link } from 'react-router-dom';
import { FiActivity, FiBarChart2, FiBookOpen, FiClipboard, FiCompass, FiUploadCloud } from 'react-icons/fi';
import { GroupedBarChart } from '../components/Charts';
import { useAuth } from '../context/useAuth';
import './education-center.css';

const OVERVIEW_ITEMS = [
  { title: 'Khóa học đang học', value: '06', note: '2 khóa mới tuần này' },
  { title: 'Bài học hoàn thành', value: '42', note: 'Tăng 8% so với tuần trước' },
  { title: 'Điểm trung bình', value: '86%', note: 'Top 20% trong lớp' },
  { title: 'Bài kiểm tra sắp tới', value: '03', note: 'Nhắc lịch tự động đã bật' },
];

const CHART_CATEGORIES = [
  { key: 'week-1', label: 'Tuần 1', completed: 62, target: 70 },
  { key: 'week-2', label: 'Tuần 2', completed: 72, target: 75 },
  { key: 'week-3', label: 'Tuần 3', completed: 84, target: 80 },
  { key: 'week-4', label: 'Tuần 4', completed: 91, target: 85 },
];

export default function Home() {
  const { role } = useAuth();

  const quickLinks = role === 'teacher'
    ? [
      { to: '/teacher/classrooms', label: 'Quản lý lớp học', icon: FiCompass },
      { to: '/teacher/assessments', label: 'Tạo bài kiểm tra', icon: FiClipboard },
      { to: '/teacher/analytics', label: 'Dashboard giáo viên', icon: FiBarChart2 },
      { to: '/upload', label: 'Tải lên tài liệu', icon: FiUploadCloud },
    ]
    : [
      { to: '/learning-path', label: 'Lộ trình học', icon: FiBookOpen },
      { to: '/assessments', label: 'Kiểm tra & Quiz', icon: FiClipboard },
      { to: '/progress', label: 'Tiến độ học tập', icon: FiActivity },
      { to: '/analytics', label: 'Dashboard phân tích', icon: FiBarChart2 },
    ];

  return (
    <div className='edu-page'>
      <section className='edu-hero'>
        <div>
          <p className='edu-eyebrow'>Education Center</p>
          <h2>Trang chủ học tập thông minh cho học sinh & giáo viên</h2>
          <p className='edu-muted'>
            Theo dõi lộ trình học, kết quả kiểm tra, phân tích hiệu suất và quản lý lớp học trên một giao diện nhất quán cho mọi thiết bị.
          </p>
        </div>
      </section>

      <section className='edu-stat-grid'>
        {OVERVIEW_ITEMS.map((item) => (
          <article key={item.title} className='edu-stat-card'>
            <p>{item.title}</p>
            <strong>{item.value}</strong>
            <span>{item.note}</span>
          </article>
        ))}
      </section>

      <section className='edu-grid-2'>
        <div className='edu-card'>
          <h3>Truy cập nhanh các tính năng chính</h3>
          <div className='edu-link-grid'>
            {quickLinks.map(({ to, label, icon: Icon }) => (
              <Link key={to} to={to} className='edu-quick-link'>
                <Icon />
                <span>{label}</span>
              </Link>
            ))}
          </div>
        </div>

        <div className='edu-card'>
          <h3>Tình trạng hệ thống lớp học</h3>
          <ul className='edu-status-list'>
            <li><span className='dot ok' /> LMS ổn định và sẵn sàng</li>
            <li><span className='dot warn' /> 2 bài nộp đang chờ chấm tự luận</li>
            <li><span className='dot ok' /> Đồng bộ điểm danh thành công</li>
          </ul>
        </div>
      </section>

      <section>
        <GroupedBarChart
          title='Tiến độ học tập theo tuần'
          subtitle='So sánh tỷ lệ hoàn thành và mục tiêu đặt ra.'
          categories={CHART_CATEGORIES}
          series={[{ key: 'completed', label: 'Đã hoàn thành' }, { key: 'target', label: 'Mục tiêu' }]}
          maxValue={100}
        />
      </section>
    </div>
  );
}
