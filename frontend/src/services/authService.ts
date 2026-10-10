import api, { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY } from './api'
import { errorMessageFromResponse } from './errors'
import type { TokenResponse, User } from '../types'

export interface LoginPayload {
  email: string
  password: string
}

export interface RegisterPayload extends LoginPayload {
  full_name?: string
}

export interface ProfileUpdate {
  full_name: string
}

export function storeTokens(tokens: TokenResponse): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token)
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
}

export function hasStoredToken(): boolean {
  return localStorage.getItem(ACCESS_TOKEN_KEY) !== null
}

export async function login(payload: LoginPayload): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>('/auth/login', payload)
  storeTokens(data)
  return data
}

export async function register(payload: RegisterPayload): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>('/auth/register', payload)
  storeTokens(data)
  return data
}

export async function logout(): Promise<void> {
  const refresh = localStorage.getItem(REFRESH_TOKEN_KEY)
  try {
    await api.post('/auth/logout', { refresh_token: refresh })
  } finally {
    clearTokens()
  }
}

export async function getMe(): Promise<User> {
  const { data } = await api.get<User>('/auth/me')
  return data
}

export async function updateMe(payload: ProfileUpdate): Promise<User> {
  const { data } = await api.put<User>('/auth/me', payload)
  return data
}

export function googleLoginUrl(): string {
  const base: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
  return `${base}/api/v1/auth/google`
}

export function getErrorMessage(error: unknown, fallback: string): string {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const response = (error as { response?: Parameters<typeof errorMessageFromResponse>[0] }).response
    const message = errorMessageFromResponse(response)
    if (message) return message
  }
  return fallback
}
