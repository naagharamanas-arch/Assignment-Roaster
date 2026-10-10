import axios, { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import api, { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY } from '../services/api'

function respond(config: InternalAxiosRequestConfig, status: number, data: unknown) {
  return { data, status, statusText: '', headers: {}, config }
}

describe('api refresh single-flight', () => {
  const originalAdapter = api.defaults.adapter

  beforeEach(() => {
    localStorage.setItem(ACCESS_TOKEN_KEY, 'old-access')
    localStorage.setItem(REFRESH_TOKEN_KEY, 'old-refresh')
  })

  afterEach(() => {
    api.defaults.adapter = originalAdapter
    vi.restoreAllMocks()
    localStorage.clear()
  })

  function installAdapter(): void {
    const adapter: AxiosAdapter = (config) => {
      const ok = config.headers.Authorization === 'Bearer new-access'
      if (ok) return Promise.resolve(respond(config, 200, { ok: true }))
      return Promise.reject(
        new AxiosError('unauthorized', 'ERR_BAD_REQUEST', config, null, respond(config, 401, {})),
      )
    }
    api.defaults.adapter = adapter
  }

  it('makes exactly one /auth/refresh call for parallel 401s', async () => {
    installAdapter()
    const post = vi.spyOn(axios, 'post').mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(
            () =>
              resolve({
                data: { access_token: 'new-access', refresh_token: 'new-refresh', token_type: 'bearer' },
              }),
            20,
          ),
        ),
    )
    const results = await Promise.all([api.get('/a'), api.get('/b'), api.get('/c'), api.get('/d')])
    expect(results.map((r) => r.status)).toEqual([200, 200, 200, 200])
    expect(post).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBe('new-refresh')
  })

  it('retries with the new token when another tab already rotated it', async () => {
    installAdapter()
    const post = vi.spyOn(axios, 'post')
    const pending = api.get('/a')
    // Another tab stores fresh tokens before our 401 is handled.
    localStorage.setItem(ACCESS_TOKEN_KEY, 'new-access')
    localStorage.setItem(REFRESH_TOKEN_KEY, 'new-refresh')
    const res = await pending
    expect(res.status).toBe(200)
    expect(post).not.toHaveBeenCalled()
  })

  it('uses the other tab result when refresh fails because the token was rotated', async () => {
    installAdapter()
    vi.spyOn(axios, 'post').mockImplementation(() => {
      localStorage.setItem(ACCESS_TOKEN_KEY, 'new-access')
      localStorage.setItem(REFRESH_TOKEN_KEY, 'new-refresh')
      return Promise.reject(new Error('401'))
    })
    const res = await api.get('/a')
    expect(res.status).toBe(200)
  })
})
