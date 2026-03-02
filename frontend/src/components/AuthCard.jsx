export default function AuthCard({ title, subtitle, children, footer }) {
  return (
    <div className='auth-shell'>
      <div className='auth-card'>
        <h1>{title}</h1>
        <p className='auth-subtitle'>{subtitle}</p>
        {children}
        {footer ? <div className='auth-footer'>{footer}</div> : null}
      </div>
    </div>
  );
}
