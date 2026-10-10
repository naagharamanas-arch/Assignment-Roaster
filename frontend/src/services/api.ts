import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import type { TokenResponse } from '../types'

const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const BASE_URL = `${API_URL}/api/v1`

export const ACCESS_TOKEN_KEY = 'access_token'
export const REFRESH_TOKEN_KEY = 'refresh_token'

interface RetryableConfig extends InternalAxiosRequestConfig {
  _retry?: boolean
}

const api = axios.create({ baseURL: BASE_URL })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

function redirectToLogin(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  if (window.location.pathname !== '/login') window.location.assign('/login')
}

/** Shared by every concurrent 401 so exactly one /auth/refresh call is made. */
let refreshPromise: Promise<void> | null = null

async function performRefresh(): Promise<void> {
  const refresh = localStorage.getItem(REFRESH_TOKEN_KEY)
  if (!refresh) throw new Error('No refresh token')
  try {
    const { data } = await axios.post<TokenResponse>(`${BASE_URL}/auth/refresh`, {
      refresh_token: refresh,
    })
    localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token)
    localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token)
  } catch (err) {
    // Another tab may have rotated the token first; if storage changed, use its result.
    const latest = localStorage.getItem(REFRESH_TOKEN_KEY)
    if (latest && latest !== refresh) return
    throw err
  }
}

function refreshOnce(): Promise<void> {
  refreshPromise ??= performRefresh().finally(() => {
    refreshPromise = null
  })
  return refreshPromise
}

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as RetryableConfig | undefined
    const isAuthCall = original?.url?.startsWith('/auth/login') || original?.url?.startsWith('/auth/refresh')
    if (error.response?.status === 401 && original && !original._retry && !isAuthCall) {
      original._retry = true
      const sent = original.headers?.Authorization
      const current = localStorage.getItem(ACCESS_TOKEN_KEY)
      // The token we sent is stale because this or another tab already refreshed: just retry.
      if (current && sent && sent !== `Bearer ${current}`) return api(original)
      try {
        await refreshOnce()
      } catch {
        redirectToLogin()
        return Promise.reject(error)
      }
      return api(original)
    }
    return Promise.reject(error)
  },
)

export default api
