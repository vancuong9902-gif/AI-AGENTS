import { useMemo, useState } from 'react';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Modal from '../ui/Modal';
import Banner from '../ui/Banner';
import PageHeader from '../ui/PageHeader';

const QUESTIONS = [
  { id: 1, difficulty: 'easy', topic: 'hàm', q: 'Hàm trong Python được định nghĩa bằng từ khóa nào?', options: ['func', 'def', 'lambda', 'return'], correct: 1 },
  { id: 2, difficulty: 'medium', topic: 'vòng lặp', q: 'Câu lệnh nào bỏ qua phần còn lại của vòng lặp hiện tại?', options: ['stop', 'continue', 'break', 'pass'], correct: 1 },
  { id: 3, difficulty: 'hard', topic: 'dữ liệu', q: 'Kiểu dữ liệu nào là immutable?', options: ['list', 'dict', 'set', 'tuple'], correct: 3 },
];

export default function Quiz() {
  const duration = 900;
  const [answers, setAnswers] = useState({});
  const [done, setDone] = useState(false);
  const [openConfirm, setOpenConfirm] = useState(false);

  const score = useMemo(() => {
    let correct = 0;
    QUESTIONS.forEach((q) => { if (answers[q.id] === q.correct) correct += 1; });
    return Math.round((correct / QUESTIONS.length) * 100);
  }, [answers]);
  const classify = score >= 85 ? 'Giỏi' : score >= 70 ? 'Khá' : score >= 50 ? 'Trung bình' : 'Yếu';

  return (
    <div className='container grid-12'>
      <Card className='span-12'>
        <PageHeader title='Placement Quiz' subtitle='Timer, progress và submit confirm theo chuẩn UX quiz.' breadcrumbs={['Student', 'Placement Quiz']} right={<Banner tone='info'>⏱ {Math.floor(duration / 60)} phút</Banner>} />
      </Card>
      <Card className='span-12 stack-md'>
        <div className='row'><strong>Tiến độ:</strong> {Object.keys(answers).length}/{QUESTIONS.length}</div>
        {QUESTIONS.map((q, idx) => (
          <div key={q.id} className='ui-card'>
            <div className='row'><strong>Câu {idx + 1}</strong><span style={{ color: 'var(--muted)' }}>{q.topic} · {q.difficulty}</span></div>
            <p>{q.q}</p>
            <div className='stack-sm'>
              {q.options.map((op, i) => <label key={op}><input type='radio' name={`q-${q.id}`} checked={answers[q.id] === i} onChange={() => setAnswers((p) => ({ ...p, [q.id]: i }))} /> {op}</label>)}
            </div>
          </div>
        ))}
        <div className='row'>
          <Button variant='primary' onClick={() => setOpenConfirm(true)}>Nộp bài</Button>
        </div>
      </Card>

      {done ? (
        <Card className='span-12 stack-sm'>
          <h2 className='section-title'>Kết quả</h2>
          <Banner tone='success'>Điểm: {score} · Phân loại: {classify}</Banner>
          <Banner tone='info'>CTA: Bắt đầu học theo lộ trình cá nhân hoá.</Banner>
        </Card>
      ) : null}

      <Modal
        open={openConfirm}
        title='Xác nhận nộp bài'
        onClose={() => setOpenConfirm(false)}
        actions={<><Button onClick={() => setOpenConfirm(false)}>Huỷ</Button><Button variant='primary' onClick={() => { setDone(true); setOpenConfirm(false); }}>Xác nhận nộp</Button></>}
      >
        Bạn đã chắc chắn nộp bài chưa? Sau khi nộp hệ thống sẽ chấm điểm ngay.
      </Modal>
    </div>
  );
}
