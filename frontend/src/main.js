const app = document.querySelector('#app');

const state = {
  token: localStorage.getItem('token') || '',
  user: null,
  loading: false,
  error: '',
  hasCourse: false,
};

function authHeaders(json = false) {
  const headers = {};
  if (json) headers['Content-Type'] = 'application/json';
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  return headers;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message || payload?.error || payload?.detail?.message || payload?.detail || 'Request failed');
  return payload;
}

async function login(email, password) {
  const payload = await api('/api/auth/login', {
    method: 'POST',
    headers: authHeaders(true),
    body: JSON.stringify({ email, password }),
  });
  const token = payload?.data?.token?.access_token || payload?.data?.access_token;
  if (!token) throw new Error('Cannot acquire access token');
  state.token = token;
  localStorage.setItem('token', token);
}

async function loadSession() {
  if (!state.token) return;
  state.loading = true;
  state.error = '';
  render();
  try {
    const profile = await api('/api/auth/me', { headers: authHeaders() });
    state.user = profile.data;
    if (state.user?.role === 'student') {
      const gate = await api('/api/v1/ai-smart-lms/student/course-gate?has_pdf=true', { headers: authHeaders() });
      state.hasCourse = gate.has_active_course;
    }
  } catch (error) {
    state.error = error.message;
  } finally {
    state.loading = false;
    render();
  }
}

function logout() {
  state.token = '';
  state.user = null;
  state.hasCourse = false;
  localStorage.removeItem('token');
  render();
}

function layout(title, body) {
  return `
    <main class="shell">
      <header class="topbar">
        <h1>${title}</h1>
        ${state.token ? '<button id="logout-btn" class="ghost">Logout</button>' : ''}
      </header>
      ${state.error ? `<p class="error">${state.error}</p>` : ''}
      ${body}
    </main>
  `;
}

function renderLogin() {
  app.innerHTML = layout('AI Smart LMS', `
    <section class="card auth-card">
      <h2>Login</h2>
      <p class="muted">Teacher and Student role-based dashboard</p>
      <form id="login-form" class="stack">
        <input name="email" type="email" required placeholder="teacher1@demo.local" />
        <input name="password" type="password" required placeholder="password" />
        <button type="submit">Sign in</button>
      </form>
      <p id="login-error" class="error"></p>
    </section>
  `);

  document.querySelector('#login-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = new FormData(event.target);
    const errorNode = document.querySelector('#login-error');
    errorNode.textContent = '';
    try {
      await login(formData.get('email'), formData.get('password'));
      await loadSession();
    } catch (error) {
      errorNode.textContent = error.message;
    }
  });
}

function renderTeacherDashboard() {
  app.innerHTML = layout('Teacher Dashboard', `
    <section class="grid two-col">
      <article class="card"><h3>PDF Upload</h3><p>Upload textbook PDF for AI processing.</p></article>
      <article class="card"><h3>Class Management</h3><p>Create class, add students, assign PDF.</p></article>
      <article class="card"><h3>Exam Generation</h3><p>Generate randomized exams and export DOCX.</p></article>
      <article class="card"><h3>Analytics</h3><p>Track entry vs final exam progress and learning time.</p></article>
    </section>
  `);
  document.querySelector('#logout-btn')?.addEventListener('click', logout);
}

function renderStudentDashboard() {
  const noCourse = '<article class="card"><h3>No course available yet.</h3><p>Wait for your teacher to upload textbook PDF.</p></article>';
  const learning = `
    <section class="grid two-col">
      <article class="card"><h3>Entry Diagnostic Test</h3><p>Timed, auto-graded, 3-level breakdown.</p></article>
      <article class="card"><h3>Personalized Learning Path</h3><p>Adaptive sessions, exercises, homework.</p></article>
      <article class="card"><h3>AI Tutor</h3><p>Restricted to uploaded PDF and current topic only.</p></article>
      <article class="card"><h3>Final Exam + AI Evaluation</h3><p>Timed final exam with strengths/weakness report.</p></article>
    </section>
  `;
  app.innerHTML = layout('Student Dashboard', state.hasCourse ? learning : noCourse);
  document.querySelector('#logout-btn')?.addEventListener('click', logout);
}

function renderLoading() {
  app.innerHTML = layout('AI Smart LMS', '<section class="card"><p>Loading...</p></section>');
}

function render() {
  if (state.loading) return renderLoading();
  if (!state.token) return renderLogin();
  if (!state.user) return renderLoading();
  if (state.user.role === 'teacher') return renderTeacherDashboard();
  return renderStudentDashboard();
}

render();
loadSession();
