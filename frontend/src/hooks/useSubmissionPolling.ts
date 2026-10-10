import { useCallback, useEffect, useState } from 'react'
import { submissionService } from '../services/submissionService'
import type { Submission } from '../types'

export const POLL_INTERVAL_MS = 2000
/** Total time to keep polling before showing the "taking longer" state. */
export const POLL_MAX_MS = 5 * 60 * 1000
const MAX_CONSECUTIVE_ERRORS = 3

/** Back-off schedule: 2s, 3s, then 5s. `base` scales it (tests pass a tiny value). */
export function nextDelay(attempt: number, base: number): number {
  const factor = attempt === 0 ? 1 : attempt === 1 ? 1.5 : 2.5
  return Math.round(base * factor)
}

interface PollingState {
  submission: Submission | null
  error: string | null
  timedOut: boolean
  setSubmission: (s: Submission) => void
  restart: () => void
}

/**
 * Polls GET /submissions/:id until the status is done or failed. Backs off,
 * pauses while the tab is hidden, and gives up after POLL_MAX_MS (`timedOut`).
 */
export function useSubmissionPolling(
  id: string | undefined,
  intervalMs: number = POLL_INTERVAL_MS,
  maxMs: number = POLL_MAX_MS,
): PollingState {
  const [submission, setSubmission] = useState<Submission | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [timedOut, setTimedOut] = useState(false)
  const [runKey, setRunKey] = useState(0)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let failures = 0
    let attempt = 0
    let stopped = false
    const startedAt = Date.now()

    const schedule = (): void => {
      timer = setTimeout(() => void tick(), nextDelay(attempt, intervalMs))
      attempt += 1
    }

    const tick = async (): Promise<void> => {
      if (cancelled) return
      if (document.hidden) return // resumed by the visibilitychange listener
      if (Date.now() - startedAt >= maxMs) {
        stopped = true
        setTimedOut(true)
        return
      }
      try {
        const next = await submissionService.get(id)
        if (cancelled) return
        failures = 0
        setError(null)
        setSubmission(next)
        if (next.status === 'done' || next.status === 'failed') {
          stopped = true
          return
        }
      } catch (err) {
        if (cancelled) return
        failures += 1
        if (failures >= MAX_CONSECUTIVE_ERRORS) {
          stopped = true
          setError(err instanceof Error ? err.message : 'Failed to load submission.')
          return
        }
      }
      schedule()
    }

    const onVisibility = (): void => {
      if (stopped) return
      if (timer) clearTimeout(timer)
      if (!document.hidden) void tick()
    }
    document.addEventListener('visibilitychange', onVisibility)
    void tick()

    return () => {
      cancelled = true
      document.removeEventListener('visibilitychange', onVisibility)
      if (timer) clearTimeout(timer)
    }
  }, [id, intervalMs, maxMs, runKey])

  const restart = useCallback(() => {
    setError(null)
    setTimedOut(false)
    setRunKey((k) => k + 1)
  }, [])

  return { submission, error, timedOut, setSubmission, restart }
}
