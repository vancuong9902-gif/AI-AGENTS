import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from '../lib/rechartsCompat';
import { apiJson } from '../lib/api';
import PageContainer from '../ui/PageContainer';
import SectionHeader from '../ui/SectionHeader';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Badge from '../ui/Badge';
import EmptyState from '../ui/EmptyState';
import LoadingState from '../ui/LoadingState';
import ErrorState from '../ui/ErrorState';
import './unified-pages.css';

const DIFFICULTY_LABELS = { easy: 'Dễ', medium: 'Trung bình', hard: 'Khó' };
const PIE_COLORS = ['#6366f1', '#14b8a6', '#f59e0b', '#ef4444', '#8b5cf6', '#0ea5e9'];

function asNumber(v, fallback = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function levelTone(levelKey) {
  const key = String(levelKey || '').toLowerCase();
  if (key === 'gioi') return { label: 'Giỏi', tone: 'success' };
  if (key === 'kha') return { label: 'Khá', tone: 'info' };
  if (key === 'trung_binh') return { label: 'Trung bình', tone: 'warning' };
  return { label: 'Yếu', tone: 'danger' };
}

export default function Result() {
  const { attemptId } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    let mounted = true;
    async function loadResult() {
      if (!attemptId) {
        setError('Thiếu attemptId trong URL.');
        setLoading(false);
        return;
      }
      setLoading(true);
      setError('');
      try {
        const data = await apiJson(`/attempts/${encodeURIComponent(attemptId)}/result`);
        if (!mounted) return;
        setDetail(data?.result_detail || null);
      } catch (e) {
        if (!mounted) return;
        setError(e?.message || 'Không thể tải kết quả.');
      } finally {
        if (mounted) setLoading(false);
      }
    }
    loadResult();
    return () => { mounted = false; };
  }, [attemptId]);

  const topicChartData = useMemo(() => {
    const rows = detail?.summary?.by_topic || {};
    return Object.entries(rows)
      .map(([topic, value]) => ({ name: topic, percent: asNumber(value?.percent, 0) }))
      .sort((a, b) => b.percent - a.percent)
      .slice(0, 8);
  }, [detail]);

  const difficultyChartData = useMemo(() => {
    const rows = detail?.summary?.by_difficulty || {};
    return ['easy', 'medium', 'hard'].map((key) => ({
      key,
      name: DIFFICULTY_LABELS[key],
      percent: asNumber(rows?.[key]?.percent, 0),
    }));
  }, [detail]);

  const weakestTopic = topicChartData?.[topicChartData.length - 1]?.name || 'nội dung vừa làm';
  const level = levelTone(detail?.classification);

  return (
    <PageContainer className='stack-md'>
      <SectionHeader title='Kết quả bài làm' subtitle='Tổng hợp năng lực theo chủ đề và độ khó.' action={<Button onClick={() => navigate('/quiz')}>Làm lại</Button>} />

      {loading ? <LoadingState title='Đang tải kết quả...' description='Hệ thống đang tổng hợp điểm và phân loại năng lực.' /> : null}

      {!loading && (error || !detail) ? (
        <div className='stack-sm'>
          <ErrorState
            title='Không thể hiển thị kết quả'
            description={error || 'Không có dữ liệu kết quả.'}
            actionLabel='Tải lại'
            onAction={() => window.location.reload()}
          />
          <EmptyState title='Vui lòng thử lại' description='Bạn có thể quay về trang quiz hoặc xem danh sách assessments.' icon='📉' />
          <div className='row'>
            <Link to='/quiz'><Button variant='primary'>Làm quiz</Button></Link>
            <Link to='/assessments'><Button>Bài assessments</Button></Link>
          </div>
        </div>
      ) : null}

      {!loading && !error && detail ? (
        <div className='result-grid'>
          <Card className='result-span-8 stack-md'>
            <div className='row'>
              <h3>Tổng quan</h3>
              <Badge tone={level.tone}>{level.label}</Badge>
            </div>
            <p className='result-score'>{Math.round(asNumber(detail?.score_percent, 0))}%</p>
            <p className='text-muted'>Điểm mạnh nhất: {topicChartData?.[0]?.name || 'Đang cập nhật'} · Cần cải thiện: {weakestTopic}</p>
          </Card>

          <Card className='result-span-4 stack-sm'>
            <h3>Hành động</h3>
            <Button variant='primary' onClick={() => navigate('/learning-path')}>Xem lộ trình học</Button>
            <Button onClick={() => navigate('/tutor')}>Hỏi AI Tutor</Button>
          </Card>

          <Card className='result-span-8'>
            <h3>Điểm theo chủ đề</h3>
            <div className='result-chart'>
              <ResponsiveContainer>
                <BarChart data={topicChartData}>
                  <XAxis dataKey='name' hide />
                  <YAxis domain={[0, 100]} />
                  <Tooltip formatter={(v) => `${v}%`} />
                  <Bar dataKey='percent' radius={[8, 8, 0, 0]} fill='#2563eb' />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card className='result-span-4'>
            <h3>Phân bố theo độ khó</h3>
            <div className='result-chart'>
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={difficultyChartData} dataKey='percent' nameKey='name' innerRadius={46} outerRadius={76}>
                    {difficultyChartData.map((_, index) => <Cell key={index} fill={PIE_COLORS[index % PIE_COLORS.length]} />)}
                  </Pie>
                  <Tooltip formatter={(value) => `${value}%`} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <ul className='result-topic-list'>
              {difficultyChartData.map((item) => <li key={item.key}>{item.name}: {item.percent}%</li>)}
            </ul>
          </Card>
        </div>
      ) : null}
    </PageContainer>
  );
}
