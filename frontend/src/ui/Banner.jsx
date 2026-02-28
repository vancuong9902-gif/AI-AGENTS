export default function Banner({ tone = 'info', children }) {
  return <div className={`banner ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>{children}</div>;
}
