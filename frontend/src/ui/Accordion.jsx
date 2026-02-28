import { useState } from 'react';
import './theme.css';

export function AccordionItem({ title, right, children, defaultOpen=false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className='acc-item'>
      <button className='acc-head' onClick={()=>setOpen(!open)}>
        <span>{title}</span>
        <span>{right || (open ? '−' : '+')}</span>
      </button>
      {open ? <div className='acc-body'>{children}</div> : null}
    </div>
  );
}

export function Accordion({ children }) {
  return <div className='acc-list'>{children}</div>;
}
