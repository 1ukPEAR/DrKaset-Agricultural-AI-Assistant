import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// Attach token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('drkaset_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Auto-logout on 401
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('drkaset_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authAPI = {
  register: (email, password) =>
    api.post('/auth/register', { email, password }),
  login: (email, password) =>
    api.post('/auth/login', { email, password }),
  refresh: (access_token) =>
    api.post('/auth/refresh', { access_token }),
}

// ── Chat ──────────────────────────────────────────────────────────────────────
export const chatAPI = {
  listSessions: () => api.get('/chat/sessions'),
  getMessages: (session_id) => api.get(`/chat/sessions/${session_id}/messages`),
  deleteSession: (session_id) => api.delete(`/chat/sessions/${session_id}`),
  // streaming is handled separately via fetch()
}

// ── Health ────────────────────────────────────────────────────────────────────
export const healthAPI = {
  check: () => api.get('/health'),
}

export const weatherAPI = {
  current: (params) => api.get('/weather', { params }),
}

export const marketPriceAPI = {
  list: () => api.get('/market-prices'),
}

export default api
