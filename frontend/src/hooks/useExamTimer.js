import { useEffect, useRef, useState } from "react";

export default function useExamTimer(initialSeconds = 0, { enabled = false } = {}) {
  const [timeLeftSec, setTimeLeftSec] = useState(Math.max(0, Number(initialSeconds) || 0));
  const initialRef = useRef(Math.max(0, Number(initialSeconds) || 0));

  useEffect(() => {
    const normalized = Math.max(0, Number(initialSeconds) || 0);
    initialRef.current = normalized;
    setTimeLeftSec(normalized);
  }, [initialSeconds]);

  useEffect(() => {
    if (!enabled || timeLeftSec <= 0) return undefined;
    const timerId = window.setInterval(() => {
      setTimeLeftSec((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => window.clearInterval(timerId);
  }, [enabled, timeLeftSec]);

  const reset = (nextSeconds = initialRef.current) => {
    setTimeLeftSec(Math.max(0, Number(nextSeconds) || 0));
  };

  return { timeLeftSec, setTimeLeftSec, reset };
import { useEffect, useMemo, useRef, useState } from 'react';

export function useExamTimer({ totalSeconds = 0, onTimeUp, onWarning }) {
  const [timeLeft, setTimeLeft] = useState(Math.max(0, Number(totalSeconds) || 0));
  const [warningLevel, setWarningLevel] = useState('normal');
  const intervalRef = useRef(null);
  const warnedRef = useRef(new Set());

  useEffect(() => {
    setTimeLeft(Math.max(0, Number(totalSeconds) || 0));
    warnedRef.current = new Set();
  }, [totalSeconds]);

  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (totalSeconds <= 0) return undefined;

    intervalRef.current = setInterval(() => {
      setTimeLeft((prev) => {
        const next = Math.max(0, prev - 1);

        if (next <= 60) setWarningLevel('critical');
        else if (next <= 300) setWarningLevel('warning');
        else setWarningLevel('normal');

        if ([600, 300, 60, 30].includes(next) && !warnedRef.current.has(next)) {
          warnedRef.current.add(next);
          onWarning?.(next);
        }

        if (next <= 0) {
          clearInterval(intervalRef.current);
          onTimeUp?.();
        }

        return next;
      });
    }, 1000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [onTimeUp, onWarning, totalSeconds]);

  const formattedTime = useMemo(() => {
    const secs = Math.max(0, Number(timeLeft) || 0);
    const h = Math.floor(secs / 3600);
    const m = String(Math.floor((secs % 3600) / 60)).padStart(2, '0');
    const s = String(secs % 60).padStart(2, '0');
    return h > 0 ? `${h}:${m}:${s}` : `${m}:${s}`;
  }, [timeLeft]);

  return { timeLeft, formattedTime, warningLevel };
}
