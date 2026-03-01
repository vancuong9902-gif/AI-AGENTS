export default function Modal({ open, title, children, onClose, actions }) {
  if (!open) return null;
  return (
    <div className='modal-backdrop' onClick={onClose}>
      <div className='modal-card' onClick={(e) => e.stopPropagation()} role='dialog' aria-modal='true' aria-label={title}>
        <h3 className='modal-title'>{title}</h3>
        <div>{children}</div>
        <div className='modal-actions'>{actions}</div>
      </div>
    </div>
  );
}
