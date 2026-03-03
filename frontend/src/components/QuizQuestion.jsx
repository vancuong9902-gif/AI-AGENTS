import React from 'react';

export default function QuizQuestion({
  question,
  onAnswer,
  answered,
  showExplanation,
  onPrev,
  onNext,
  onSubmit,
  isFirst,
  isLast,
}) {
  const selected = answered?.selected;

  return (
    <div className="card stack">
      <h3>{question?.question}</h3>

      <div className="stack">
        {(question?.options || []).map((opt, idx) => {
          const isSelected = selected === opt;
          const isCorrect = opt === question?.correct_answer;
          const showState = showExplanation && selected;

          const classNames = [
            'option-row',
            isSelected ? 'selected' : '',
            showState && isCorrect ? 'correct' : '',
            showState && isSelected && !isCorrect ? 'wrong' : '',
          ].join(' ');

          return (
            <button key={`${question?.id}-${idx}`} type="button" className={classNames} onClick={() => onAnswer?.(opt)}>
              <span>{String.fromCharCode(65 + idx)}.</span>
              <span>{opt}</span>
            </button>
          );
        })}
      </div>

      {showExplanation && question?.explanation && (
        <div className="alert info">
          <strong>AI Explanation:</strong> {question.explanation}
        </div>
      )}

      <div className="row-between">
        <button className="ghost" onClick={onPrev} disabled={isFirst}>← Prev</button>
        {!isLast ? (
          <button onClick={onNext}>Next →</button>
        ) : (
          <button className="success-btn" onClick={onSubmit}>Submit</button>
        )}
      </div>
    </div>
  );
}
