import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  FiActivity,
  FiBarChart2,
  FiBookOpen,
  FiCalendar,
  FiChevronRight,
  FiClipboard,
  FiCompass,
  FiHeart,
  FiPlayCircle,
  FiTrendingUp,
  FiUploadCloud,
} from 'react-icons/fi';
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

const COURSE_SECTIONS = [
  {
    key: 'new',
    icon: FiCompass,
    title: 'Khóa học mới',
    items: ['Prompt Engineering cơ bản', 'SQL cho phân tích dữ liệu', 'Lộ trình học React thực chiến'],
  },
  {
    key: 'hot',
    icon: FiTrendingUp,
    title: 'Khóa học đang hot',
    items: ['Machine Learning nhập môn', 'Kỹ năng thuyết trình số', 'Thiết kế UX cho LMS'],
  },
  {
    key: 'favorite',
    icon: FiHeart,
    title: 'Được yêu thích nhất',
    items: ['Python cho người mới', 'Toán tư duy THPT', 'Ôn luyện IELTS nền tảng'],
  },
];

const LESSON_STEPS = [
  { label: 'Giới thiệu', done: true },
  { label: 'Video bài giảng', done: true },
  { label: 'Quiz nhanh', done: false },
  { label: 'Tổng kết', done: false },
];

const PERSONAL_PLAYLIST = ['Data Analytics căn bản', 'Kỹ năng đọc hiểu nhanh'];
const PLAYLIST_POOL = ['Node.js API thực hành', 'CSS Grid & Responsive', 'Luyện đề cuối kỳ Toán 12'];

export default function Home() {
  const { role } = useAuth();
  const [playlist, setPlaylist] = useState(PERSONAL_PLAYLIST);
  const [dragItem, setDragItem] = useState('');

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

  const progress = useMemo(() => {
    const done = LESSON_STEPS.filter((step) => step.done).length;
    return Math.round((done / LESSON_STEPS.length) * 100);
  }, []);

  const onDropToPlaylist = () => {
    if (!dragItem || playlist.includes(dragItem)) return;
    setPlaylist((prev) => [...prev, dragItem]);
    setDragItem('');
  };

  return (
    <div className='edu-page'>
      <section className='edu-hero edu-reveal'>
        <div>
          <p className='edu-eyebrow'>Education Center</p>
          <h2>Trang học tập trực quan, dễ dùng và tối ưu cho mọi thiết bị</h2>
          <p className='edu-muted'>
            Trải nghiệm tìm kiếm nhanh khóa học, theo dõi tiến độ và quản lý nội dung học tập với giao diện nhất quán light/dark mode.
          </p>
        </div>
      </section>

      <section className='edu-stat-grid edu-reveal'>
        {OVERVIEW_ITEMS.map((item) => (
          <article key={item.title} className='edu-stat-card'>
            <p>{item.title}</p>
            <strong>{item.value}</strong>
            <span>{item.note}</span>
          </article>
        ))}
      </section>

      <section className='edu-grid-2 edu-reveal'>
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

      <section className='edu-course-sections edu-reveal'>
        {COURSE_SECTIONS.map(({ key, icon: Icon, title, items }) => (
          <article key={key} className='edu-card edu-hover-lift'>
            <h3><Icon /> {title}</h3>
            <ul className='edu-list'>
              {items.map((item) => (
                <li key={item}><FiChevronRight /> {item}</li>
              ))}
            </ul>
          </article>
        ))}
      </section>

      <section className='edu-grid-2 edu-reveal'>
        <article className='edu-card'>
          <h3>Lộ trình bài học</h3>
          <progress className='edu-progress-track' aria-label='Tiến độ hoàn thành bài học' value={progress} max={100} />
          <p className='edu-muted'>{progress}% hoàn thành · Điều hướng rõ ràng qua từng bước học.</p>
          <ol className='edu-step-list'>
            {LESSON_STEPS.map((step) => (
              <li key={step.label} className={step.done ? 'done' : ''}>
                <span>{step.label}</span>
                <div className='edu-step-actions'>
                  <button type='button'>Trở lại</button>
                  <button type='button'>Tiếp theo</button>
                  <button type='button'>Hoàn thành</button>
                </div>
              </li>
            ))}
          </ol>
        </article>

        <article className='edu-card'>
          <h3><FiPlayCircle /> Danh sách học tập cá nhân (Kéo & thả)</h3>
          <p className='edu-muted'>Kéo khóa học từ kho gợi ý sang danh sách của bạn để đồng bộ nhanh giữa các thiết bị.</p>
          <div className='edu-dnd-grid'>
            <div className='edu-dnd-box'>
              <h4>Kho gợi ý</h4>
              {PLAYLIST_POOL.map((item) => (
                <button
                  key={item}
                  type='button'
                  draggable
                  onDragStart={() => setDragItem(item)}
                  className='edu-draggable'
                >
                  {item}
                </button>
              ))}
            </div>
            <div className='edu-dnd-box edu-drop-zone' onDragOver={(event) => event.preventDefault()} onDrop={onDropToPlaylist}>
              <h4>Playlist của bạn</h4>
              <ul className='edu-list'>
                {playlist.map((item) => <li key={item}><FiChevronRight /> {item}</li>)}
              </ul>
            </div>
          </div>
        </article>
      </section>

      <section className='edu-grid-2 edu-reveal'>
        <article className='edu-card edu-hover-lift'>
          <h3><FiCalendar /> Sự kiện đặc biệt</h3>
          <p className='edu-muted'>Workshop “Chiến lược học thông minh với AI” diễn ra vào 20:00 thứ 6 tuần này.</p>
        </article>
        <article className='edu-card edu-hover-lift'>
          <h3>Thành phần nội dung học tập</h3>
          <ul className='edu-list'>
            <li><FiChevronRight /> Video bài giảng có transcript.</li>
            <li><FiChevronRight /> Quiz & khảo sát đánh giá cuối bài.</li>
            <li><FiChevronRight /> Tài liệu tải về và ghi chú đồng bộ.</li>
          </ul>
        </article>
      </section>

      <section className='edu-reveal'>
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
