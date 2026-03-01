import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { FiAlertCircle, FiCheckCircle, FiInfo, FiX } from 'react-icons/fi';

const ToastContext = createContext(null);

const ICON_BY_TONE = {
  success: FiCheckCircle,
  error: FiAlertCircle,
  info: FiInfo,
};

const MAX_TOAST = 3;

export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const timersRef = useRef(new Map());

  const removeToast = useCallback((id) => {
    setItems((prev) => prev.filter((item) => item.id !== id));
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  const pushToast = useCallback(({ tone = 'info', title, message, duration = 3200 }) => {
    const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    setItems((prev) => [...prev.slice(-(MAX_TOAST - 1)), { id, tone, title, message }]);
    const timer = setTimeout(() => removeToast(id), duration);
    timersRef.current.set(id, timer);
    return id;
  }, [removeToast]);

  useEffect(() => () => {
    timersRef.current.forEach((timer) => clearTimeout(timer));
    timersRef.current.clear();
  }, []);

  const api = useMemo(() => ({
    show: pushToast,
    success: (payload) => pushToast({ ...payload, tone: 'success' }),
    error: (payload) => pushToast({ ...payload, tone: 'error' }),
    info: (payload) => pushToast({ ...payload, tone: 'info' }),
    dismiss: removeToast,
  }), [pushToast, removeToast]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className='toast-stack' role='status' aria-live='polite' aria-atomic='false'>
        {items.map((item) => {
          const Icon = ICON_BY_TONE[item.tone] || FiInfo;
          return (
            <div className={`toast toast-${item.tone}`} key={item.id}>
              <Icon aria-hidden='true' />
              <div className='stack-sm'>
                {item.title ? <strong>{item.title}</strong> : null}
                {item.message ? <span>{item.message}</span> : null}
              </div>
              <button type='button' className='toast-close focus-ring' onClick={() => removeToast(item.id)} aria-label='Đóng thông báo'>
                <FiX />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast phải được dùng trong ToastProvider');
  }
  return context;
}
