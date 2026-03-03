import React from 'react';

const STEPS = [
  'Tham gia lớp',
  'Chọn môn học',
  'Kiểm tra đầu vào',
  'Kết quả đầu vào',
  'Nhận lộ trình',
  'Học từng topic',
  'Mở khóa cuối kỳ',
  'Thi cuối kỳ',
  'Kết quả cuối kỳ',
];

export default function StudentProgressStepper({ currentStep, completedSteps = [], onStepClick }) {
  const completedSet = new Set(completedSteps);

  return (
    <div className="card stack">
      <div className="card-title">Lộ trình học tập</div>
      <div className="stepper-wrap">
        {STEPS.map((label, idx) => {
          const step = idx + 1;
          const isDone = completedSet.has(step);
          const isCurrent = currentStep === step;
          const isLocked = step > currentStep && !isDone;

          return (
            <button
              key={label}
              className={`stepper-step ${isCurrent ? 'current' : ''} ${isDone ? 'done' : ''} ${isLocked ? 'locked' : ''}`}
              onClick={() => (isDone ? onStepClick?.(step) : undefined)}
              disabled={!isDone}
              title={label}
            >
              <span className="stepper-icon">{isDone ? '✅' : isLocked ? '🔒' : step}</span>
              <span className="stepper-label">{label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
