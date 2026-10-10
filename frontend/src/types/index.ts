export type SubmissionStatus =
  | 'queued'
  | 'fetching'
  | 'analysing'
  | 'roasting'
  | 'done'
  | 'failed'

export type RoastLevel = 'mild' | 'medium' | 'savage'
export type LanguageStyle = 'tamil_script' | 'tanglish'
export type Severity = 'low' | 'medium' | 'high'

export interface User {
  id: number
  email: string
  full_name: string | null
  is_active: boolean
  is_verified: boolean
  is_admin: boolean
  oauth_provider: string | null
  created_at: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface CategoryScores {
  structure: number
  readme: number
  code_quality: number
  tests: number
  git_hygiene: number
  security: number
  originality: number
}

export interface AnalysisIssue {
  file: string | null
  problem: string
  severity: Severity
}

export interface Analysis {
  id: number
  submission_id?: number
  model: string
  score: number
  categories: CategoryScores
  strengths: string[]
  issues: AnalysisIssue[]
  prompt_tokens?: number
  completion_tokens?: number
}

export interface Roast {
  id: number
  submission_id?: number
  title: string
  roast_text: string
  one_liner: string | null
  fixes: string[]
  model?: string
  share_slug: string
  is_public: boolean
  created_at: string
}

export interface Submission {
  id: number
  user_id?: number
  repo_url: string
  owner: string
  repo: string
  commit_sha: string | null
  assignment_brief: string | null
  roast_level: RoastLevel
  language_style: LanguageStyle
  status: SubmissionStatus
  error: string | null
  created_at: string
  score?: number | null
  analysis?: Analysis | null
  roast?: Roast | null
}

export interface SubmissionCreate {
  repo_url: string
  assignment_brief?: string
  roast_level: RoastLevel
  language_style: LanguageStyle
}

