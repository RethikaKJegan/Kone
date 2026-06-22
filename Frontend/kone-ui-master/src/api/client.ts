import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'

interface RetryableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean
}

interface RefreshResponse {
  access: { token: string; expires: string }
  refresh: { token: string; expires: string }
}

let refreshPromise: Promise<RefreshResponse> | null = null

function clearStoredAuth() {
  localStorage.removeItem('salesnxt_token')
  localStorage.removeItem('salesnxt_refresh_token')
  localStorage.removeItem('salesnxt_user')
}

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
  return config
})

apiClient.interceptors.response.use(
  response => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetryableRequestConfig | undefined

    if (
      error.response?.status !== 401 ||
      !originalRequest ||
      originalRequest._retry ||
      originalRequest.url?.includes('/auth/login') ||
      originalRequest.url?.includes('/auth/register') ||
      originalRequest.url?.includes('/auth/refresh-tokens')
    ) {
      return Promise.reject(error)
    }

    const refreshToken = localStorage.getItem('salesnxt_refresh_token')
    if (!refreshToken) {
      return Promise.reject(error)
    }

    originalRequest._retry = true

    try {
      refreshPromise ??= apiClient
        .post<RefreshResponse>('/auth/refresh-tokens', { refreshToken })
        .then(({ data }) => data)
        .finally(() => {
          refreshPromise = null
        })

      const data = await refreshPromise

      localStorage.setItem('salesnxt_token', data.access.token)
      localStorage.setItem('salesnxt_refresh_token', data.refresh.token)
      originalRequest.headers.Authorization = `Bearer ${data.access.token}`

      return apiClient(originalRequest)
    } catch (refreshError) {
      clearStoredAuth()
      if (!window.location.pathname.includes('/signin')) {
        window.location.assign('/signin')
      }
      return Promise.reject(refreshError)
    }
  }
)

export default apiClient
