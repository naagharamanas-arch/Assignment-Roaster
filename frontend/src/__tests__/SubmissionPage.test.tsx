import { ChakraProvider, defaultSystem } from '@chakra-ui/react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextDelay } from '../hooks/useSubmissionPolling'
import { SubmissionPage } from '../pages/SubmissionPage'
import { submissionService } from '../services/submissionService'
import type { Submission } from '../types'

vi.mock('../services/submissionService', () => ({
  submissionService: {
    get: vi.fn(),
    regenerate: vi.fn(),
    setVisibility: vi.fn(),
  },
}))

const base: Submission = {
  id: 7,
  user_id: 1,
  repo_url: 'https://github.com/octocat/hello',
  owner: 'octocat',
  repo: 'hello',
  commit_sha: null,
  assignment_brief: null,
  roast_level: 'medium',
  language_style: 'tanglish',
  status: 'queued',
  error: null,
  created_at: '2026-01-01T00:00:00Z',
}

const XSS = '<img src=x onerror=alert(1)> <script>alert(2)</script>'

const done: Submission = {
  ...base,
  status: 'done',
  analysis: {
    id: 1, submission_id: 7, model: 'm', score: 72,
    categories: { structure: 80, readme: 60, code_quality: 70, tests: 20, git_hygiene: 90, security: 85, originality: 50 },
    strengths: ['Clean layout'],
    issues: [{ file: 'a.py', problem: 'No tests', severity: 'high' }],
    prompt_tokens: 1, completion_tokens: 1,
  },
  roast: {
    id: 3, submission_id: 7, title: 'Title', roast_text: XSS, one_liner: 'one',
    fixes: ['Add tests'], model: 'm', share_slug: 'abc', is_public: false, created_at: '2026-01-01T00:00:00Z',
  },
}

function renderPage(maxPollMs?: number) {
  return render(
    <ChakraProvider value={defaultSystem}>
      <MemoryRouter initialEntries={['/submissions/7']}>
        <Routes>
          <Route path="/submissions/:id" element={<SubmissionPage pollMs={10} maxPollMs={maxPollMs} />} />
        </Routes>
      </MemoryRouter>
    </ChakraProvider>,
  )
}

describe('SubmissionPage', () => {
  beforeEach(() => vi.mocked(submissionService.get).mockReset())

  it('polls until done, then renders the result with roast text escaped', async () => {
    vi.mocked(submissionService.get)
      .mockResolvedValueOnce(base)
      .mockResolvedValueOnce({ ...base, status: 'analysing' })
      .mockResolvedValue(done)
    const { container } = renderPage()

    expect(await screen.findByText(/Queued/)).toBeInTheDocument()
    expect(await screen.findByRole('img', { name: /Score 72/ }, { timeout: 2000 })).toBeInTheDocument()
    expect(screen.getByTestId('roast-text').textContent).toBe(XSS)
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img[src="x"]')).toBeNull()
    expect(screen.getByText('Add tests')).toBeInTheDocument()
    expect(vi.mocked(submissionService.get).mock.calls.length).toBeGreaterThanOrEqual(3)
  })

  it('stops polling after done', async () => {
    vi.mocked(submissionService.get).mockResolvedValue(done)
    renderPage()
    await screen.findByRole('img', { name: /Score 72/ })
    await new Promise((r) => setTimeout(r, 60))
    expect(submissionService.get).toHaveBeenCalledTimes(1)
  })

  it('shows the error for failed submissions', async () => {
    vi.mocked(submissionService.get).mockResolvedValue({ ...base, status: 'failed', error: 'Repo not found' })
    renderPage()
    expect(await screen.findByText('Repo not found')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /try again/i })).toBeInTheDocument()
  })

  it('shows a taking-longer state with a refresh button after the poll budget', async () => {
    vi.mocked(submissionService.get).mockResolvedValue({ ...base, status: 'analysing' })
    renderPage(80)
    expect(await screen.findByText(/taking longer than expected/i, undefined, { timeout: 2000 })).toBeInTheDocument()
    const calls = vi.mocked(submissionService.get).mock.calls.length
    await userEvent.click(screen.getByRole('button', { name: 'Refresh' }))
    await waitFor(() => expect(vi.mocked(submissionService.get).mock.calls.length).toBeGreaterThan(calls))
  })

  it('does not poll while the tab is hidden and resumes when visible', async () => {
    vi.mocked(submissionService.get).mockResolvedValue({ ...base, status: 'analysing' })
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true })
    renderPage()
    await new Promise((r) => setTimeout(r, 100))
    expect(submissionService.get).not.toHaveBeenCalled()
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false })
    document.dispatchEvent(new Event('visibilitychange'))
    await waitFor(() => expect(submissionService.get).toHaveBeenCalled())
  })

  it('backs off 2s, 3s, then 5s', () => {
    expect([0, 1, 2, 3].map((n) => nextDelay(n, 2000))).toEqual([2000, 3000, 5000, 5000])
  })
})

