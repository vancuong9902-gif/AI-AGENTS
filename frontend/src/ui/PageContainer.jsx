import './theme.css';

export default function PageContainer({ className = '', children }) {
  return <div className={`page-container ${className}`.trim()}>{children}</div>;
}
