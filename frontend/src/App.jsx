import Navbar from './components/Navbar';
import AppRoutes from './routes/AppRoutes';
import { useAuth } from './context/AuthContext';
import './App.css';

function App() {
  const { role, userId } = useAuth();

  return (
    <div className='app-shell'>
      <aside className='sidebar'>
        <Navbar />
      </aside>
      <div className='main-wrap'>
        <header className='topbar'>
          <div className='topbar-inner'>
            <div>
              <strong>Nền tảng xử lý học liệu AI</strong>
              <div style={{ color: 'var(--muted)', fontSize: 13 }}>Upload · Library · Topics detail · Regenerate · Quiz-ready</div>
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
