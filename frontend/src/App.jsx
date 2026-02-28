import { useState } from 'react';
import Navbar from './components/Navbar';
import AppRoutes from './routes/AppRoutes';
import { useAuth } from './context/AuthContext';
import './App.css';

function App() {
  const { role, userId } = useAuth();
  const [open, setOpen] = useState(false);

  return (
    <div className='app-shell'>
      <aside className={`sidebar ${open ? 'open' : ''}`}>
        <Navbar onNavigate={() => setOpen(false)} />
      </aside>
      <div className='main-wrap'>
        <header className='topbar'>
          <div className='topbar-inner'>
            <div className='row'>
              <button className='nav-toggle focus-ring' aria-label='Mở menu điều hướng' onClick={() => setOpen((v) => !v)}>☰</button>
              <div>
                <strong>AI-AGENTS LMS</strong>
                <div style={{ color: 'var(--muted)', fontSize: 13 }}>Dashboard · Upload · Library · Quiz · Reports</div>
              </div>
            </div>
            <div className='user-pill'>{(role || 'guest').toUpperCase()} · #{userId ?? 1}</div>
          </div>
        </header>
        <main className='page-content'>
          <AppRoutes />
        </main>
      </div>
    </div>
  );
}

export default App;
