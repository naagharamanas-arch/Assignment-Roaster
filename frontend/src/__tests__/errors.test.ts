import { describe, expect, it } from 'vitest'
import { getErrorMessage } from '../services/authService'
import { detailMessage, errorMessageFromResponse, oauthErrorMessage } from '../services/errors'

describe('detailMessage', () => {
  it('handles string, array, object and legacy slowapi shapes', () => {
    expect(detailMessage({ detail: 'Nope' })).toBe('Nope')
    expect(detailMessage({ detail: [{ msg: 'Field required', loc: ['body', 'x'] }] })).toBe('Field required')
    expect(detailMessage({ detail: { message: 'Limit hit' } })).toBe('Limit hit')
    expect(detailMessage({ error: '5 per 1 minute' })).toContain('5 per 1 minute')
    expect(detailMessage(null)).toBeNull()
    expect(detailMessage({})).toBeNull()
  })
})

describe('error messages', () => {
  it('appends Retry-After to 429s without timing info', () => {
    const msg = errorMessageFromResponse({ status: 429, data: { error: '5 per 1 minute' }, headers: { 'retry-after': '30' } })
    expect(msg).toContain('Try again in 30 seconds')
  })

  it('does not duplicate timing already in the body', () => {
    const msg = errorMessageFromResponse({
      status: 429,
      data: { detail: 'Too many requests, try again in 30s' },
      headers: { 'retry-after': '30' },
    })
    expect(msg).toBe('Too many requests, try again in 30s')
  })

  it('getErrorMessage reads array details and falls back', () => {
    expect(getErrorMessage({ response: { status: 422, data: { detail: [{ msg: 'bad email' }] } } }, 'fb')).toBe('bad email')
    expect(getErrorMessage(new Error('x'), 'fb')).toBe('fb')
  })
})

describe('oauthErrorMessage', () => {
  it('maps known codes and falls back for unknown ones', () => {
    expect(oauthErrorMessage(null)).toBeNull()
    expect(oauthErrorMessage('account_disabled')).toMatch(/disabled/i)
    expect(oauthErrorMessage('weird')).toMatch(/try again/i)
  })
})
