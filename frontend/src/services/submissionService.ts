import axios from 'axios'
import api from './api'
import { errorMessageFromResponse } from './errors'
import type {
  LanguageStyle,
  Roast,
  RoastLevel,
  Submission,
  SubmissionCreate,
  CategoryScores,
} from '../types'

/** Public roast payload (GET /roasts/{slug}). Extra fields are optional. */
export interface PublicRoast {
  title: string
  roast_text: string
  one_liner: string | null
  fixes: string[]
  share_slug: string
  created_at: string
  score?: number | null
  categories?: CategoryScores | null
  owner?: string | null
  repo?: string | null
  roast_level?: RoastLevel
  language_style?: LanguageStyle
}

export interface RegenerateOptions {
  roast_level: RoastLevel
  language_style: LanguageStyle
}

export class RateLimitError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'RateLimitError'
  }
}

/** Convert any thrown value into an Error with a user-friendly message. */
export function toFriendlyError(err: unknown): Error {
  if (axios.isAxiosError(err)) {
    const detail = errorMessageFromResponse(err.response)
    if (err.response?.status === 429) {
      return new RateLimitError(
        detail ?? 'Daily limit reached (3 roasts per day, 1 per repo per hour).',
      )
    }
    if (detail) return new Error(detail)
    if (!err.response) return new Error('Cannot reach the server. Check your connection.')
    return new Error(`Request failed (${err.response.status}).`)
  }
  return err instanceof Error ? err : new Error('Something went wrong.')
}

async function call<T>(fn: () => Promise<{ data: T }>): Promise<T> {
  try {
    return (await fn()).data
  } catch (err) {
    throw toFriendlyError(err)
  }
}

export const submissionService = {
  create: (payload: SubmissionCreate): Promise<Submission> =>
    call(() => api.post<Submission>('/submissions', payload)),

  list: async (params?: { limit?: number; offset?: number }): Promise<Submission[]> => {
    const data = await call(() =>
      api.get<Submission[] | { items: Submission[] }>('/submissions', { params }),
    )
    return Array.isArray(data) ? data : data.items
  },

  get: (id: number | string): Promise<Submission> =>
    call(() => api.get<Submission>(`/submissions/${id}`)),

  remove: async (id: number | string): Promise<void> => {
    await call(() => api.delete<void>(`/submissions/${id}`))
  },

  regenerate: (id: number | string, options: RegenerateOptions): Promise<Submission> =>
    call(() => api.post<Submission>(`/submissions/${id}/roast/regenerate`, options)),

  getPublicRoast: (slug: string): Promise<PublicRoast> =>
    call(() => api.get<PublicRoast>(`/roasts/${encodeURIComponent(slug)}`)),

  setVisibility: (roastId: number, isPublic: boolean): Promise<Roast> =>
    call(() => api.put<Roast>(`/roasts/${roastId}/visibility`, { is_public: isPublic })),
}


