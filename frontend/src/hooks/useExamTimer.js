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
}
