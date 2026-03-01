import Button from './Button';

export default function ErrorState({ title = 'Đã xảy ra lỗi', description, actionLabel, onAction }) {
  return (
    <div className='error-state' role='alert'>
      <div className='error-state-icon' aria-hidden='true'>⚠️</div>
      <h3>{title}</h3>
      {description ? <p>{description}</p> : null}
      {actionLabel ? <Button variant='primary' onClick={onAction}>{actionLabel}</Button> : null}
    </div>
  );
}
