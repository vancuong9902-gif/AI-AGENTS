// Centralized API helper for the demo frontend.
// Backend uses prefix /api and (mostly) returns an envelope: { request_id, data, error }.
//
// IMPORTANT (Docker demo): Default to same-origin "/api" so the Vite dev server can proxy
// requests to the backend container. This avoids browser CORS issues when the frontend is
// opened via a LAN/"Network" IP (e.g. 172.x / LAN IP) instead of "localhost".

export const API_BASE = (import.meta?.env?.VITE_API_URL || import.meta?.env?.VITE_API_BASE_URL || "/api").replace(/\/+$/, "");


export function buildAuthHeaders(extra = {}) {
  const headers = { ...extra, "Cache-Control": "no-cache" };
  const token = localStorage.getItem("token") || localStorage.getItem("access_token") || localStorage.getItem("jwt");
  if (token && !headers.Authorization) headers.Authorization = `Bearer ${token}`;
  const uid = localStorage.getItem("user_id");
  const role = localStorage.getItem("role");
  if (uid && !headers["X-User-Id"]) headers["X-User-Id"] = uid;
  if (role && !headers["X-User-Role"]) headers["X-User-Role"] = role;
  return headers;
}

function _isEnvelope(obj) {
  return obj && typeof obj === "object" && ("data" in obj || "error" in obj);
}

function _mkError(message, body, status) {
  const err = new Error(message || `HTTP ${status}`);
  err.status = status;

  // Backend standard: { request_id, data, error: {code, message, details} }
  if (_isEnvelope(body) && body?.error) {
    err.code = body.error.code;
    err.details = body.error.details;
    err.request_id = body.request_id;
    return err;
  }

  // FastAPI plain detail shape (fallback)
  if (body && typeof body === "object" && body.detail) {
    const d = body.detail;
    if (d && typeof d === "object") {
      err.code = d.code;
      err.details = d;
    }
  }

  return err;
}

export async function apiJson(path, options = {}) {
  const url = path.startsWith("http")
    ? path
    : `${API_BASE}${path.startsWith("/") ? "" : "/"}${path}`;

  // Avoid stale GETs after mutations (teacher grading, leaderboards...).
  // Also makes debugging easier when the browser caches aggressively.
  const headers = buildAuthHeaders(options.headers || {});

  // Auto-JSON encode plain objects when caller didn't stringify.
  let body = options.body;
  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;
  if (body && !isFormData && typeof body === "object" && !(body instanceof Blob) && !(body instanceof ArrayBuffer)) {
    if (!headers["Content-Type"]) headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }

  const res = await fetch(url, {
    cache: "no-store",
    ...options,
    body,
    headers,
  });

  // If backend returns plain text, surface it.
  const text = await res.text();
  let respBody = null;
  try {
    respBody = text ? JSON.parse(text) : null;
  } catch {
    respBody = text;
  }

  if (!res.ok) {
    const msg =
      typeof respBody === "string"
        ? respBody
        : respBody?.detail || respBody?.error?.message || JSON.stringify(respBody);
    throw _mkError(msg, respBody, res.status);
  }

  // Unwrap envelope if present.
  if (_isEnvelope(respBody)) {
    if (respBody?.error) {
      const msg = respBody.error?.message || JSON.stringify(respBody.error);
      throw _mkError(msg, respBody, res.status);
    }
    return respBody?.data ?? respBody;
  }

  return respBody;
}
