import axios from 'axios'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: Number(import.meta.env.VITE_API_TIMEOUT) || 15000,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
})

apiClient.interceptors.request.use(config => {
  const token = localStorage.getItem('salesnxt_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  if (config.data instanceof FormData) {
    delete config.headers['Content-Type']
  }
  return config
})

apiClient.interceptors.response.use(
  response => response,
  async error => {
    const originalRequest = error.config
    const refreshToken = localStorage.getItem('salesnxt_refresh_token')

    if (error.response?.status !== 401 || !refreshToken || originalRequest?._retry) {
      return Promise.reject(error)
    }

    originalRequest._retry = true
    try {
      const { data } = await axios.post(
        `${apiClient.defaults.baseURL}/auth/refresh-tokens`,
        { refreshToken }
      )
      const accessToken = data.access?.token
      const nextRefreshToken = data.refresh?.token
      if (accessToken) {
        localStorage.setItem('salesnxt_token', accessToken)
        originalRequest.headers.Authorization = `Bearer ${accessToken}`
      }
      if (nextRefreshToken) {
        localStorage.setItem('salesnxt_refresh_token', nextRefreshToken)
      }
      return apiClient(originalRequest)
    } catch (refreshError) {
      localStorage.removeItem('salesnxt_token')
      localStorage.removeItem('salesnxt_refresh_token')
      localStorage.removeItem('salesnxt_user')
      return Promise.reject(refreshError)
    }
  }
)

export default apiClient
