import React from 'react';

export default function Alert({ type = 'info', message }) {
  if (!message) return null;
  return <div className={`alert ${type}`}>{message}</div>;
}
