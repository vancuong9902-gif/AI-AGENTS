export function Breadcrumbs({ items = [] }) {
  if (!items.length) return null;
  return <div className='breadcrumbs'>{items.map((i, idx) => <span key={`${i}-${idx}`}>{idx > 0 ? ' / ' : ''}{i}</span>)}</div>;
}

export default function PageHeader({ title, subtitle, breadcrumbs = [], right }) {
  return (
    <div className='page-header'>
      <div className='stack-sm'>
        <Breadcrumbs items={breadcrumbs} />
        <h1 className='page-title'>{title}</h1>
        {subtitle ? <p className='page-subtitle'>{subtitle}</p> : null}
      </div>
      {right}
    </div>
  );
}
