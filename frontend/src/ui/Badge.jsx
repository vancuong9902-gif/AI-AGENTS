import './theme.css';
export default function Badge({ tone='warning', children }) { return <span className={`badge ${tone}`}>{children}</span>; }
