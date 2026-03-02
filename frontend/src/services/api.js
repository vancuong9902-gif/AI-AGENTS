const API = import.meta.env.VITE_API_URL;

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });

  const raw = await response.text();
  let data = null;
  try {
    data = raw ? JSON.parse(raw) : null;
  } catch {
    data = raw;
  }

  if (!response.ok) {
    const error = new Error(typeof data === 'string' ? data : data?.message || data?.detail || 'Request failed');
    error.status = response.status;
    error.payload = data;
    throw error;
  }

  return data;
}

export function loginApi(payload) {
  return request('/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function registerApi(payload) {
  return request('/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function withAuthHeaders(extraHeaders = {}, tokenOverride) {
  const token = tokenOverride || localStorage.getItem('token');
  if (!token) {
    return extraHeaders;
  }

  return {
    ...extraHeaders,
    Authorization: `Bearer ${token}`,
  };
}

export function meApi(tokenOverride) {
  return request('/auth/me', {
    headers: withAuthHeaders({}, tokenOverride),
  });
}
