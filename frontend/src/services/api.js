import axios from 'axios';
import { toast } from 'react-toastify';

// Microservices API Gateway URL
const API_URL = import.meta.env.VITE_API_GATEWAY_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_URL,
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    toast.error(error.response?.data?.error || 'An error occurred');
    return Promise.reject(error);
  }
);

export const authAPI = {
  login: (data) => api.post('/api/auth/login', data),
  register: (data) => api.post('/api/auth/register', data),
};

export const faqAPI = {
  ask: (question) => api.post('/api/faq/ask', question),
  getPopular: () => api.get('/api/faq/popular'),
  getCategories: () => api.get('/api/faq/categories'),
};

export const coordinatorAPI = {
  ask: (query, context) => api.post('/api/coordinator/ask', { query, context }),
  getAgents: () => api.get('/api/coordinator/agents'),
};

export const payrollAPI = {
  //query: (query) => api.post('/api/payroll/query', { query }),
  query: (data) => api.post('/api/payroll/query', data ),
  getPayslip: (employeeId) => api.get(`/api/payroll/payslip/${employeeId}`),
  getHistory: (employeeId) => api.get(`/api/payroll/history/${employeeId}`),
};

export const recruitmentAPI = {
  //query: (query, context) => api.post('/api/recruitment/query', { query, context }),
  query: (data) => api.post('/api/recruitment/query', data),
  getOpenings: (params) => api.get('/api/recruitment/openings', { params }),
  getOpening: (id) => api.get(`/api/recruitment/opening/${id}`),
};


export const performanceAPI = {
  //query: (query, employeeId) => api.post('/api/performance/query', { query, employee_id: employeeId }),
  query: (data) => api.post('/api/performance/query', data),
  getGoals: (employeeId) => api.get(`/api/performance/goals?employee_id=${employeeId}`),
  createGoal: (data, employeeId) => api.post('/api/performance/goal/create', { ...data, employee_id: employeeId }),
  updateGoal: (data) => api.put('/api/performance/goal/update', data),
  getReviews: (employeeId) => api.get(`/api/performance/reviews?employee_id=${employeeId}`),
};


export const leaveAPI = {
  //query: (query) => api.post('/api/leave/query', { query }),
  query: (data) => api.post('/api/leave/query', data),
  request: (data) => api.post('/api/leave/request', data),
  getBalance: (employeeId) => api.get(`/api/leave/balance?employee_id=${employeeId}`),
  getHistory: () => api.get('/api/leave/history'),
};

export default api;
