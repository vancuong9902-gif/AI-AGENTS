import Spinner from './Spinner';

export default function LoadingState({ title = 'Đang tải dữ liệu...', description, compact = false }) {
  return (
    <div className={`loading-state ${compact ? 'loading-state-compact' : ''}`.trim()} role='status' aria-live='polite'>
      <Spinner />
      <div className='stack-sm'>
        <strong>{title}</strong>
        {description ? <p>{description}</p> : null}
      </div>
    </div>
  );
}
