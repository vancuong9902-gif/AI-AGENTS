import React from 'react';

export default function EmptyState({ icon = '📚', title, description, action = null }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      {title && <div className="card-title">{title}</div>}
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}
