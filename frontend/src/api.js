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

  // Teacher – Courses management
  getMyCourses: () => api.get('/mvp/teacher/courses'),
  generateFinalExam: (courseId) => api.post(`/mvp/courses/${courseId}/generate-final-exam`),

  // Teacher – Classrooms
  createClassroom: (name, description) => api.post('/teacher/classrooms', { name, description }),
  getMyClassrooms: () => api.get('/teacher/classrooms'),
  getClassroomDashboard: (classroomId) => api.get(`/teacher/classrooms/${classroomId}/dashboard`),
  getStudentReports: (classroomId) => api.get(`/teacher/classroom/${classroomId}/student-reports`),
  assignLearningPlan: (classroomId, courseId) => api.post(`/teacher/classrooms/${classroomId}/assign-learning-plan`, { course_id: courseId }),
  exportClassReportPDF: (classroomId) => api.get(`/classrooms/${classroomId}/reports/latest/export`, {
    params: { format: 'pdf' },
    responseType: 'blob',
  }),
  exportClassReportExcel: (classroomId, reportId) => api.get(`/classrooms/${classroomId}/reports/${reportId}/export/excel`, {
    responseType: 'blob',
  }),

  // Teacher – Exam Word export
  generateExamDocx: (courseId, numVariants, numQuestions, examType) => api.post(
    '/exams/generate-variants',
    {
      course_id: courseId,
      num_variants: numVariants,
      questions_per_variant: numQuestions,
      exam_type: examType,
    },
    { responseType: 'blob' },
  ),
  exportExamVariantsZip: (batchId) => api.get(`/exams/variants/${batchId}/export`, {
    params: { format: 'zip' },
    responseType: 'blob',
  }),

  // Teacher – Analytics
  getAnalytics: (userId, documentId) => api.get('/analytics/composite', {
    params: { user_id: userId, document_id: documentId, window_days: 30 },
  }),
  getAnalyticsHistory: (userId) => api.get('/analytics/history', { params: { user_id: userId } }),

  // Student – Course selection
  getAvailableCourses: () => api.get('/mvp/student/courses'),
  getMyClasses: () => api.get('/classrooms'),
  joinClassroom: (code) => api.post('/classrooms/join', { code }),

  // Student – Learning plan
  getLearningPlan: (userId, classroomId) => api.get(`/learning-plans/${userId}/current`, {
    params: classroomId ? { classroom_id: classroomId } : {},
  }),
  completeTask: (planId, taskId, topicId) => api.post(`/learning-plans/${planId}/tasks/complete`, {
    task_id: taskId,
    topic_id: topicId,
  }),

  // Student – Homework
  getHomework: (topicId, userId) => api.get('/v1/homework', { params: { topicId, userId } }),
  submitHomeworkAnswer: (homeworkId, answer, userId) => api.post(`/v1/homework/${homeworkId}/answer`, { answer, user_id: userId }),

  // Student – Final exam
  getFinalExam: (courseId) => api.get(`/mvp/student/courses/${courseId}/final-exam`).catch(() => api.get('/mvp/student/exams/latest')),
  submitFinalExam: (examId, answers) => api.post(`/mvp/student/exams/${examId}/submit`, { answers }),

  // Notifications
  getNotifications: () => api.get('/notifications/my'),
  markNotificationRead: (id) => api.post(`/notifications/${id}/mark-read`),
};

export default api;

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
