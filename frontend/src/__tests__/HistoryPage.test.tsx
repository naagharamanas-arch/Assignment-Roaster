import { ChakraProvider, defaultSystem } from '@chakra-ui/react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { HistoryPage } from '../pages/HistoryPage'
import { submissionService } from '../services/submissionService'
import type { Submission } from '../types'

vi.mock('../services/submissionService', () => ({
  submissionService: { list: vi.fn(), remove: vi.fn() },
}))

function sub(id: number, repo: string, status: Submission['status'] = 'done'): Submission {
  return {
    id,
    user_id: 1,
    repo_url: `https://github.com/octocat/${repo}`,
    owner: 'octocat',
    repo,
    commit_sha: null,
    assignment_brief: null,
    roast_level: 'medium',
    language_style: 'tanglish',
    status,
    error: null,
    created_at: '2026-01-01T00:00:00Z',
  }
}

function renderPage() {
  return render(
    <ChakraProvider value={defaultSystem}>
      <MemoryRouter>
        <HistoryPage />
      </MemoryRouter>
    </ChakraProvider>,
  )
}

describe('HistoryPage', () => {
  beforeEach(() => {
    vi.mocked(submissionService.list).mockReset()
    vi.mocked(submissionService.remove).mockReset()
  })

  it('lists submissions with status and links to detail pages', async () => {
    vi.mocked(submissionService.list).mockResolvedValue([sub(1, 'alpha'), sub(2, 'beta', 'failed')])
    renderPage()
    expect(await screen.findByText('octocat/alpha')).toBeInTheDocument()
    expect(screen.getByText('octocat/beta')).toBeInTheDocument()
    expect(screen.getByText('done')).toBeInTheDocument()
    expect(screen.getByText('failed')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'octocat/alpha' })).toHaveAttribute(
      'href',
      '/submissions/1',
    )
  })

  it('shows an empty state with a link to submit', async () => {
    vi.mocked(submissionService.list).mockResolvedValue([])
    renderPage()
    expect(await screen.findByText(/no roasts yet/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /roast a repo/i })).toHaveAttribute('href', '/submit')
  })

  it('deletes a submission and removes only that row', async () => {
    vi.mocked(submissionService.list).mockResolvedValue([sub(1, 'alpha'), sub(2, 'beta')])
    vi.mocked(submissionService.remove).mockResolvedValue(undefined)
    renderPage()
    await screen.findByText('octocat/alpha')
    await userEvent.click(screen.getByRole('button', { name: 'Delete octocat/alpha' }))
    await waitFor(() => expect(screen.queryByText('octocat/alpha')).not.toBeInTheDocument())
    expect(submissionService.remove).toHaveBeenCalledWith(1)
    expect(screen.getByText('octocat/beta')).toBeInTheDocument()
  })

  it('keeps the row and shows an error when delete fails', async () => {
    vi.mocked(submissionService.list).mockResolvedValue([sub(1, 'alpha')])
    vi.mocked(submissionService.remove).mockImplementation(async () => { throw new Error('Delete exploded') })
    renderPage()
    await screen.findByText('octocat/alpha')
    await userEvent.click(screen.getByRole('button', { name: 'Delete octocat/alpha' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Delete exploded')
    expect(screen.getByText('octocat/alpha')).toBeInTheDocument()
  })

  it('shows an error when the list fails to load', async () => {
    vi.mocked(submissionService.list).mockImplementation(async () => { throw new Error('Cannot reach the server.') })
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the server.')
  })

  it('shows the score from the list item and works when it is missing', async () => {
    vi.mocked(submissionService.list).mockResolvedValue([
      { ...sub(1, 'alpha'), score: 88 },
      sub(2, 'beta'),
    ])
    renderPage()
    await screen.findByText('octocat/alpha')
    const scores = screen.getAllByLabelText('score')
    expect(scores).toHaveLength(1)
    expect(scores[0]).toHaveTextContent('88')
  })

  it('loads more using the offset when a full page is returned', async () => {
    const first = Array.from({ length: 50 }, (_, i) => sub(i + 1, `r${i + 1}`))
    vi.mocked(submissionService.list)
      .mockResolvedValueOnce(first)
      .mockResolvedValueOnce([sub(51, 'last')])
    renderPage()
    await screen.findByText('octocat/r1')
    await userEvent.click(screen.getByRole('button', { name: 'Load more' }))
    expect(await screen.findByText('octocat/last')).toBeInTheDocument()
    expect(submissionService.list).toHaveBeenLastCalledWith({ limit: 50, offset: 50 })
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
  })

  it('hides Load more for a short page', async () => {
    vi.mocked(submissionService.list).mockResolvedValue([sub(1, 'alpha')])
    renderPage()
    await screen.findByText('octocat/alpha')
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
  })
})

