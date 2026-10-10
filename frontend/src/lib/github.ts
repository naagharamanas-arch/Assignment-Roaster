const GITHUB_URL = /^https:\/\/github\.com\/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))\/([A-Za-z0-9._-]{1,100})\/?$/

export interface UrlValidation {
  valid: boolean
  error: string | null
  owner?: string
  repo?: string
}

/** Accepts only https://github.com/{owner}/{repo}. */
export function validateGithubUrl(input: string): UrlValidation {
  const value = input.trim()
  if (!value) return { valid: false, error: 'Enter a GitHub repository URL.' }
  const match = GITHUB_URL.exec(value)
  if (!match) {
    return { valid: false, error: 'Use the form https://github.com/owner/repo' }
  }
  const repo = match[2]
  if (repo === '.' || repo === '..') return { valid: false, error: 'Invalid repository name.' }
  return { valid: true, error: null, owner: match[1], repo }
}

export const TAMIL_FONT = "'Noto Sans Tamil', 'Latha', 'Nirmala UI', 'Tamil Sangam MN', sans-serif"
