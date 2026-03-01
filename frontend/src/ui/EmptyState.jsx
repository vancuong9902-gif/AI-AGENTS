import Button from './Button';

export default function EmptyState({ icon = '📚', title, description, actionLabel, onAction }) {
  return (
    <div className='empty-state' role='status'>
      <div className='empty-icon' aria-hidden='true'>{icon}</div>
      <h3>{title}</h3>
      {description ? <p>{description}</p> : null}
      {actionLabel ? <Button variant='primary' onClick={onAction}>{actionLabel}</Button> : null}
    </div>
  );
}
