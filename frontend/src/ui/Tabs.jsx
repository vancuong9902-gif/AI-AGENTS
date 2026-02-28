export function Tabs({ tabs, value, onChange }) {
  return (
    <div className='tabs' role='tablist'>
      {tabs.map((t) => (
        <button
          key={t.value}
          type='button'
          className={`tab-btn focus-ring ${value === t.value ? 'active' : ''}`}
          onClick={() => onChange(t.value)}
          role='tab'
          aria-selected={value === t.value}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
