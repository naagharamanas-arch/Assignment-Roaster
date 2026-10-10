import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../context/AuthContext'
import { useAuth } from '../hooks/useAuth'
import * as authService from '../services/authService'
import type { User } from '../types'

vi.mock('../services/authService', () => ({
  hasStoredToken: vi.fn(),
  getMe: vi.fn(),
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  clearTokens: vi.fn(),
}))

const me: User = {
  id: 1,
  email: 'a@b.co',
  full_name: 'Ada',
  is_active: true,
  is_verified: true,
  is_admin: false,
  oauth_provider: null,
  created_at: '2026-01-01T00:00:00Z',
}

const wrapper = ({ children }: { children: ReactNode }) => <AuthProvider>{children}</AuthProvider>

describe('AuthContext', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(authService.hasStoredToken).mockReturnValue(false)
  })

  it('starts logged out and not loading without a stored token', () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    expect(result.current.user).toBeNull()
    expect(result.current.loading).toBe(false)
    expect(authService.getMe).not.toHaveBeenCalled()
  })

  it('restores the session from a stored token', async () => {
    vi.mocked(authService.hasStoredToken).mockReturnValue(true)
    vi.mocked(authService.getMe).mockResolvedValue(me)
    const { result } = renderHook(() => useAuth(), { wrapper })
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toEqual(me)
  })

  it('clears tokens when the stored session is invalid', async () => {
    vi.mocked(authService.hasStoredToken).mockReturnValue(true)
    vi.mocked(authService.getMe).mockRejectedValue(new Error('401'))
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBeNull()
    expect(authService.clearTokens).toHaveBeenCalledTimes(1)
  })

  it('login stores the user returned by /me', async () => {
    vi.mocked(authService.login).mockResolvedValue({
      access_token: 'a',
      refresh_token: 'r',
      token_type: 'bearer',
    })
    vi.mocked(authService.getMe).mockResolvedValue(me)
    const { result } = renderHook(() => useAuth(), { wrapper })
    await act(async () => {
      await result.current.login('a@b.co', 'password123')
    })
    expect(authService.login).toHaveBeenCalledWith({ email: 'a@b.co', password: 'password123' })
    expect(result.current.user).toEqual(me)
  })

  it('failed login leaves the user logged out and rethrows', async () => {
    vi.mocked(authService.login).mockRejectedValue(new Error('bad creds'))
    const { result } = renderHook(() => useAuth(), { wrapper })
    await act(async () => {
      await expect(result.current.login('a@b.co', 'nope')).rejects.toThrow('bad creds')
    })
    expect(result.current.user).toBeNull()
  })

  it('register sends full_name (undefined when blank) and sets the user', async () => {
    vi.mocked(authService.register).mockResolvedValue({
      access_token: 'a',
      refresh_token: 'r',
      token_type: 'bearer',
    })
    vi.mocked(authService.getMe).mockResolvedValue(me)
    const { result } = renderHook(() => useAuth(), { wrapper })
    await act(async () => {
      await result.current.register('a@b.co', 'password123', '')
    })
    expect(authService.register).toHaveBeenCalledWith({
      email: 'a@b.co',
      password: 'password123',
      full_name: undefined,
    })
    expect(result.current.user).toEqual(me)
  })

  it('logout clears the user, even when the API call fails', async () => {
    vi.mocked(authService.login).mockResolvedValue({
      access_token: 'a',
      refresh_token: 'r',
      token_type: 'bearer',
    })
    vi.mocked(authService.getMe).mockResolvedValue(me)
    const { result } = renderHook(() => useAuth(), { wrapper })
    await act(async () => {
      await result.current.login('a@b.co', 'password123')
    })
    expect(result.current.user).not.toBeNull()

    vi.mocked(authService.logout).mockRejectedValue(new Error('network'))
    await act(async () => {
      await result.current.logout().catch(() => undefined)
    })
    expect(result.current.user).toBeNull()
  })

  it('useAuth throws outside the provider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    expect(() => renderHook(() => useAuth())).toThrow(/within AuthProvider/)
    spy.mockRestore()
  })
})
