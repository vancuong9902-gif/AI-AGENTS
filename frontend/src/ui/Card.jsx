import './theme.css';
export default function Card({ className='', ...props }) { return <div className={`ui-card ${className}`} {...props} />; }
