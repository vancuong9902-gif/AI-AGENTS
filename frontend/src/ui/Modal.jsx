export default function Modal({ open, title, children, onClose, actions }) {
  if (!open) return null;
  return (
    <div className='modal-backdrop' onClick={onClose}>
      <div className='modal-card' onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginTop: 0 }}>{title}</h3>
        <div>{children}</div>
        <div className='row' style={{ marginTop: 16, justifyContent: 'flex-end' }}>{actions}</div>
      </div>
    </div>
  );
}
