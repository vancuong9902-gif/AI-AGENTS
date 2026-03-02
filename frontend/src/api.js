import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  const userId = localStorage.getItem('userId');
  const userRole = localStorage.getItem('userRole');

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  } else if (userId) {
    config.headers['X-User-Id'] = userId;
    config.headers['X-User-Role'] = userRole || 'student';
  }

  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 || err.response?.status === 403) {
      localStorage.clear();
      window.dispatchEvent(new Event('auth:logout'));
      window.location.href = '/login';
    }
    return Promise.reject(err);
  },
);

export function getErrorMessage(error) {
  if (!error.response) {
    return 'Cannot connect to server. Please check your connection.';
  }
  if (error.response.status >= 500) {
    return 'Internal server error. Please try again.';
  }
  const detail = error.response.data?.error || error.response.data?.detail;
  if (typeof detail === 'string') return detail;
  return detail?.message || error.message || 'Request failed.';
}

export const healthApi = {
  check: () => api.get('/health'),
};

export const authApi = {
  register: (data) => api.post('/auth/register', data),
  login: (data) => api.post('/auth/login-json', data),
  me: () => api.get('/auth/me'),
};

export const mvpApi = {
  uploadCourse: (formData) => api.post('/mvp/courses/upload', formData),
  generateTopics: (courseId) => api.post(`/mvp/courses/${courseId}/generate-topics`),
  generateEntryTest: (courseId) => api.post(`/mvp/courses/${courseId}/generate-entry-test`),
  getResults: (page = 1, pageSize = 10) => api.get('/mvp/teacher/results', {
    params: { page, page_size: pageSize },
  }),
  getCourse: () => api.get('/mvp/student/course'),
  getStudentStatus: () => api.get('/mvp/student/status'),
  getLatestExam: () => api.get('/mvp/student/exams/latest'),
  submitExam: (examId, answers) => api.post(`/mvp/student/exams/${examId}/submit`, { answers }),
  askTutor: (question) => api.post('/mvp/student/tutor', { question }),
};

export default api;
