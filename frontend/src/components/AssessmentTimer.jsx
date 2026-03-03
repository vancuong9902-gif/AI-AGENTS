import React from 'react';

function formatTime(totalSeconds) {
  const mm = String(Math.floor(totalSeconds / 60)).padStart(2, '0');
  const ss = String(totalSeconds % 60).padStart(2, '0');
  return `${mm}:${ss}`;
}

export default function AssessmentTimer({
  durationSeconds,
  onExpire,
  backupKey,
  answers,
  serverStartedAt,
}) {
  const getInitial = React.useCallback(() => {
    if (serverStartedAt) {
      const elapsed = Math.max(0, Math.floor((Date.now() - new Date(serverStartedAt).getTime()) / 1000));
      return Math.max(0, durationSeconds - elapsed);
    }
    return durationSeconds;
  }, [durationSeconds, serverStartedAt]);

  const [left, setLeft] = React.useState(getInitial);

  React.useEffect(() => {
    setLeft(getInitial());
  }, [getInitial]);

  React.useEffect(() => {
    if (left <= 0) {
      onExpire?.();
      return undefined;
    }

    const t = setInterval(() => setLeft((prev) => Math.max(0, prev - 1)), 1000);
    return () => clearInterval(t);
  }, [left, onExpire]);

  React.useEffect(() => {
    if (!backupKey) return undefined;
    const backup = setInterval(() => {
      localStorage.setItem(backupKey, JSON.stringify(answers || {}));
    }, 30000);
    return () => clearInterval(backup);
  }, [answers, backupKey]);

  let timerClass = '';
  if (left <= 60) timerClass = 'critical';
  else if (left <= 300) timerClass = 'warning';

  return (
    <div className={`assessment-timer ${timerClass}`}>
      ⏱ {formatTime(left)}
    </div>
  );
}
