import Navbar from './components/Navbar';
import AppRoutes from './routes/AppRoutes';
import './App.css';

function App() {
  return (
    <div className='app-shell'>
      <aside className='sidebar'>
        <Navbar />
      </aside>
      <div className='main-wrap'>
        <header className='topbar'>
          <div>Hệ thống quản lý học liệu và topics AI</div>
        </header>
        <main className='page-content'>
          <AppRoutes />
        </main>
      </div>
    </div>
  );
}

export default App;
