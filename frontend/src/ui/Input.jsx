import './theme.css';

export default function Input({ label, helper, id, ...props }) {
  if (!label && !helper) return <input id={id} className='input' {...props} />;
  return (
    <label className='input-wrap' htmlFor={id}>
      {label ? <span className='input-label'>{label}</span> : null}
      <input id={id} className='input' {...props} />
      {helper ? <span className='input-helper'>{helper}</span> : null}
    </label>
  );
}
