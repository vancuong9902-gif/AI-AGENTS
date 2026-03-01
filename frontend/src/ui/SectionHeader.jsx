import './theme.css';

export default function SectionHeader({ title, subtitle, action, className = '' }) {
  return (
    <div className={`section-header ${className}`.trim()}>
      <div className='stack-sm'>
        <h2 className='section-header-title'>{title}</h2>
        {subtitle ? <p className='section-header-subtitle'>{subtitle}</p> : null}
      </div>
      {action ? <div className='section-header-action'>{action}</div> : null}
    </div>
  );
}
