import { useState } from 'react';
import './theme.css';
export function AccordionItem({ title, children, defaultOpen=false }) {
  const [open, setOpen] = useState(defaultOpen);
  return <div className='acc-item'><button className='acc-head' onClick={()=>setOpen(!open)}>{title}</button>{open ? <div className='acc-body'>{children}</div> : null}</div>;
}
