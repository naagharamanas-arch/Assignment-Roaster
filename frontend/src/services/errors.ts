/** Shared helpers to turn API error bodies into human-readable text. */

function messageOf(item: unknown): string | null {
  if (typeof item === 'string') return item
  if (typeof item === 'object' && item !== null) {
    const msg = (item as { msg?: unknown; message?: unknown })
    if (typeof msg.msg === 'string') return msg.msg
    if (typeof msg.message === 'string') return msg.message
  }
  return null
}

/**
 * Extract a message from an error body. Handles `detail` as a string, an array
 * (FastAPI 422 list), an object with `message` (+ optional `reset_at`), and the
 * legacy slowapi shape `{ "error": "..." }`.
 */
export function detailMessage(data: unknown): string | null {
  if (typeof data !== 'object' || data === null) return null
  const body = data as { detail?: unknown; error?: unknown }
  const detail = body.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const first = detail.map(messageOf).find((m): m is string => m !== null)
    return first ?? null
  }
  if (typeof detail === 'object' && detail !== null) {
    const d = detail as { message?: unknown; reset_at?: unknown }
    const msg = typeof d.message === 'string' ? d.message : null
    const reset = typeof d.reset_at === 'string' ? d.reset_at : null
    if (msg && reset) return `${msg} Resets at ${new Date(reset).toLocaleString()}.`
    return msg
  }
  if (typeof body.error === 'string') return `Too many requests: ${body.error}`
  return null
}

interface ResponseLike {
  status?: number
  data?: unknown
  headers?: unknown
}

function retryAfter(headers: unknown): string | null {
  if (typeof headers !== 'object' || headers === null) return null
  const h = headers as { get?: (name: string) => unknown } & Record<string, unknown>
  const raw = typeof h.get === 'function' ? h.get('retry-after') : h['retry-after']
  return typeof raw === 'string' || typeof raw === 'number' ? String(raw) : null
}

/** Message for any axios-like error; appends Retry-After info on 429 when the body lacks it. */
export function errorMessageFromResponse(response: ResponseLike | undefined): string | null {
  if (!response) return null
  let message = detailMessage(response.data)
  if (response.status === 429) {
    const retry = retryAfter(response.headers)
    if (retry && !(message && /\d+\s*s/.test(message))) {
      message = `${message ?? 'Too many requests.'} Try again in ${retry} seconds.`
    }
  }
  return message
}

const OAUTH_ERRORS: Record<string, string> = {
  oauth_failed: 'Google sign-in failed. Please try again.',
  oauth_state: 'Your Google sign-in session expired or was invalid. Please try again.',
  oauth_cancelled: 'Google sign-in was cancelled.',
  account_disabled: 'This account has been disabled.',
}

/** Friendly text for a `?error=` code from the OAuth callback (generic text for unknown codes). */
export function oauthErrorMessage(code: string | null): string | null {
  if (!code) return null
  return OAUTH_ERRORS[code] ?? 'Sign-in failed. Please try again.'
}
