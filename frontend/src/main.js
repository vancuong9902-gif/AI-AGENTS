const app = document.querySelector('#app');

const state = {
  token: localStorage.getItem('token') || '',
  user: null,
  assessments: [],
  templates: [],
  loading: false,
  error: '',
};

function headers(withJson = false) {
  const h = {};
  if (withJson) h['Content-Type'] = 'application/json';
  if (state.token) h.Authorization = `Bearer ${state.token}`;
  return h;
}

async function login(email, password) {
  const response = await fetch('/api/login', {
    method: 'POST',
    headers: headers(true),
    body: JSON.stringify({ email, password }),
  });

  const payload = await response.json();
  if (!response.ok || payload?.error) {
    throw new Error(payload?.error?.message || payload?.detail || 'Đăng nhập thất bại');
  }

  const token = payload?.data?.token?.access_token || payload?.data?.access_token;
  if (!token) throw new Error('Không nhận được token từ backend');

  state.token = token;
  localStorage.setItem('token', token);
}

function setLoading(value) {
  state.loading = value;
  render();
}

async function loadDashboardData() {
  setLoading(true);
  state.error = '';

  try {
    const me = await fetch('/api/auth/me', { headers: headers() });
    state.user = me.ok ? (await me.json())?.data || null : null;

    const [assessmentsRes, templatesRes] = await Promise.all([
      fetch('/api/assessments', { headers: headers() }),
      fetch('/api/exams/templates'),
    ]);

    state.assessments = assessmentsRes.ok ? (await assessmentsRes.json())?.data || [] : [];
    state.templates = templatesRes.ok ? (await templatesRes.json())?.templates || [] : [];
  } catch (error) {
    state.error = error.message;
  } finally {
    setLoading(false);
  }
}

function logout() {
  state.token = '';
  state.user = null;
  state.assessments = [];
  state.templates = [];
  localStorage.removeItem('token');
  render();
}

function renderLogin() {
  app.innerHTML = `
    <main class="container">
      <section class="card narrow">
        <h1>Đăng nhập</h1>
        <p class="muted">Frontend cơ bản để kết nối API backend.</p>
        <form id="login-form" class="stack">
          <label>Email
            <input required type="email" name="email" placeholder="teacher1@demo.local" />
          </label>
          <label>Mật khẩu
            <input required type="password" name="password" placeholder="••••••••" />
          </label>
          <button type="submit">Đăng nhập</button>
          <p id="login-error" class="error"></p>
        </form>
      </section>
    </main>
  `;

  const form = document.querySelector('#login-form');
  const errorNode = document.querySelector('#login-error');

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    errorNode.textContent = '';

    const formData = new FormData(form);
    try {
      await login(formData.get('email'), formData.get('password'));
      await loadDashboardData();
      render();
    } catch (error) {
      errorNode.textContent = error.message;
    }
  });
}

function renderList(items, emptyText, actionLabel) {
  if (!items.length) return `<p class="muted">${emptyText}</p>`;

  return `<ul class="list">${items
    .map(
      (item) => `
      <li>
        <div>
          <strong>${item.title || item.name || 'Untitled'}</strong>
          <p class="muted">ID: ${item.id || item.template_id || '-'}</p>
        </div>
        <button class="secondary" data-id="${item.id || item.template_id || ''}">${actionLabel}</button>
      </li>
    `,
    )
    .join('')}</ul>`;
}

function renderDashboard() {
  const userName = state.user?.full_name || state.user?.email || 'Người dùng';
  app.innerHTML = `
    <main class="container">
      <section class="card">
        <div class="row between">
          <div>
            <h1>Trang chính</h1>
            <p class="muted">Xin chào, ${userName}</p>
          </div>
          <button id="logout" class="secondary">Đăng xuất</button>
        </div>
      </section>

      <section class="card">
        <h2>Danh sách bài kiểm tra</h2>
        ${state.loading ? '<p>Đang tải dữ liệu...</p>' : renderList(state.assessments, 'Chưa có dữ liệu assessments.', 'Làm bài kiểm tra')}
      </section>

      <section class="card">
        <h2>Mẫu đề thi</h2>
        ${state.loading ? '<p>Đang tải dữ liệu...</p>' : renderList(state.templates, 'Không có mẫu đề.', 'Tải tài liệu')}
      </section>

      ${state.error ? `<section class="card"><p class="error">${state.error}</p></section>` : ''}
    </main>
  `;

  document.querySelector('#logout')?.addEventListener('click', logout);
  document.querySelectorAll('button[data-id]').forEach((button) => {
    button.addEventListener('click', () => {
      const id = button.getAttribute('data-id');
      window.alert(`Đã bấm thao tác cho item ID: ${id}`);
    });
  });
}

function render() {
  if (!state.token) return renderLogin();
  return renderDashboard();
}

(async function bootstrap() {
  render();
  if (state.token) {
    await loadDashboardData();
    render();
  }
})();
