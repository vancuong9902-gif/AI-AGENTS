import React from 'react';

function difficultyLabel(key) {
  if (key === 'easy') return 'Dễ';
  if (key === 'medium') return 'Trung bình';
  return 'Khó';
}

export default function ResultPage({ result, questions = [], onViewRoadmap, onRetry, title }) {
  const score = Number(result?.score || 0);
  const pass = score >= 60;
  const showConfetti = score >= 80;
  const breakdown = result?.breakdown || { easy: [0, 0], medium: [0, 0], hard: [0, 0] };

  return (
    <div className="stack">
      {showConfetti && <div className="confetti">🎉 🎊 🎉</div>}
      <div className="card stack">
        <h2>{title || 'Kết quả bài kiểm tra'}</h2>
        <div className={`result-score ${pass ? 'pass' : 'fail'}`}>{score}</div>
        <div className="badge gray">Ngưỡng đạt: 60%</div>

        <div className="row">
          {Object.entries(breakdown).map(([key, value]) => (
            <span key={key} className="badge blue">{difficultyLabel(key)} {value[0]}/{value[1]}</span>
          ))}
        </div>

        <div className="row">
          {onViewRoadmap && <button onClick={onViewRoadmap}>Xem lộ trình học</button>}
          {onRetry && <button className="ghost" onClick={onRetry}>Làm lại</button>}
        </div>
      </div>

      <div className="card stack">
        {(questions || []).map((q, idx) => {
          const correct = q.selected_answer === q.correct_answer;
          return (
            <div key={q.id || idx} className={`result-question ${correct ? 'ok' : 'bad'}`}>
              <div><strong>Câu {idx + 1}</strong> {correct ? '✓' : '✗'} {q.question}</div>
              <div>Đáp án đúng: <strong>{q.correct_answer || 'N/A'}</strong></div>
              {q.explanation && <div className="result-explanation">Giải thích: {q.explanation}</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
