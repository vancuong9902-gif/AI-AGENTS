import './theme.css';
export default function Button({ variant='default', className='', ...props }) {
  return <button className={`btn ${variant} ${className}`} {...props} />;
}
