const app = document.querySelector('#app');

const state = {
  token: localStorage.getItem('token') || '',
  user: null,
  assessments: [],
  templates: [],
  loading: false,
  error: '',
};

const REGISTER_DEFAULTS = {
  name: '',
  email: '',
  password: '',
  role: 'teacher',
  student_code: '',
};

function headers(withJson = false) {
  const h = {};
  if (withJson) h['Content-Type'] = 'application/json';
  if (state.token) h.Authorization = `Bearer ${state.token}`;
  return h;
}

function mapValidationErrors(payload) {
  const details = payload?.error?.details?.errors || payload?.detail || [];
  const fieldErrors = {};

  if (Array.isArray(details)) {
    details.forEach((item) => {
      const loc = Array.isArray(item?.loc) ? item.loc[item.loc.length - 1] : item?.field;
      if (loc) fieldErrors[loc] = item?.msg || 'Dữ liệu không hợp lệ';
    });
  }

  if (payload?.error?.field && payload?.error?.message) {
    fieldErrors[payload.error.field] = payload.error.message;
  }

  return fieldErrors;
}

function setFieldError(form, fieldName, message) {
  const node = form.querySelector(`[data-error-for="${fieldName}"]`);
  if (node) node.textContent = message || '';
}

function clearFieldErrors(form) {
  form.querySelectorAll('[data-error-for]').forEach((node) => {
    node.textContent = '';
  });
}

async function registerUser(input) {
  const requestBody = {
    name: input.name,
    email: input.email,
    password: input.password,
    role: String(input.role || 'student').toLowerCase(),
  };

  if (requestBody.role === 'student' && input.student_code) {
    requestBody.student_code = input.student_code;
  }

  const response = await fetch('/api/auth/register', {
    method: 'POST',
    headers: headers(true),
    body: JSON.stringify(requestBody),
  });

  const payload = await response.json();
  if (!response.ok || payload?.error) {
    const error = new Error(payload?.error?.message || 'Đăng ký thất bại');
    error.fieldErrors = mapValidationErrors(payload);
    error.payload = payload;
    throw error;
  }

  return payload?.data;
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

function renderRegister() {
  app.innerHTML = `
    <main class="container">
      <section class="card narrow">
        <h1>Đăng ký</h1>
        <p class="muted">Tạo tài khoản giáo viên hoặc học sinh.</p>
        <form id="register-form" class="stack">
          <label>Tên hiển thị
            <input required type="text" name="name" placeholder="cuong" />
            <span class="error" data-error-for="name"></span>
          </label>
          <label>Email
            <input required type="email" name="email" placeholder="cuong05@gmail.com" />
            <span class="error" data-error-for="email"></span>
          </label>
          <label>Mật khẩu
            <input required type="password" minlength="8" name="password" placeholder="Ít nhất 8 ký tự" />
            <span class="error" data-error-for="password"></span>
          </label>
          <label>Vai trò
            <select name="role">
              <option value="teacher" selected>teacher</option>
              <option value="student">student</option>
            </select>
            <span class="error" data-error-for="role"></span>
          </label>
          <label id="student-code-row" class="hidden">Mã học sinh
            <input type="text" name="student_code" placeholder="SV001" />
            <span class="error" data-error-for="student_code"></span>
          </label>
          <button type="submit">Đăng ký</button>
          <p id="register-status" class="muted"></p>
          <p id="register-error" class="error"></p>
          <p class="muted">Đã có tài khoản? <a href="/">Đăng nhập</a></p>
        </form>
      </section>
    </main>
  `;

  const form = document.querySelector('#register-form');
  const roleInput = form.querySelector('select[name="role"]');
  const studentCodeRow = form.querySelector('#student-code-row');
  const studentCodeInput = form.querySelector('input[name="student_code"]');
  const statusNode = document.querySelector('#register-status');
  const errorNode = document.querySelector('#register-error');

  const syncRoleState = () => {
    const isStudent = roleInput.value === 'student';
    studentCodeRow.classList.toggle('hidden', !isStudent);
    studentCodeInput.required = isStudent;
  };

  roleInput.addEventListener('change', syncRoleState);
  syncRoleState();

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearFieldErrors(form);
    errorNode.textContent = '';
    statusNode.textContent = '';

    const formData = new FormData(form);
    const formPayload = {
      ...REGISTER_DEFAULTS,
      name: String(formData.get('name') || '').trim(),
      email: String(formData.get('email') || '').trim(),
      password: String(formData.get('password') || ''),
      role: String(formData.get('role') || 'student').trim(),
      student_code: String(formData.get('student_code') || '').trim(),
    };

    try {
      const result = await registerUser(formPayload);
      statusNode.textContent = `Đăng ký thành công cho ${result?.user?.email || formPayload.email}. Bạn có thể đăng nhập.`;
      form.reset();
      roleInput.value = 'teacher';
      syncRoleState();
    } catch (error) {
      const fieldErrors = error.fieldErrors || {};
      Object.entries(fieldErrors).forEach(([field, message]) => setFieldError(form, field, message));
      errorNode.textContent = error.message || 'Đăng ký thất bại';
    }
  });
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
          <p class="muted">Chưa có tài khoản? <a href="/register">Đăng ký</a></p>
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
  if (window.location.pathname === '/register') return renderRegister();
  if (!state.token) return renderLogin();
  return renderDashboard();
}

(async function bootstrap() {
  render();
  if (window.location.pathname !== '/register' && state.token) {
    await loadDashboardData();
    render();
  }
})();
