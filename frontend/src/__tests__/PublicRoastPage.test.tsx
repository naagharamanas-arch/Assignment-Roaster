import { ChakraProvider, defaultSystem } from '@chakra-ui/react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PublicRoastPage } from '../pages/PublicRoastPage'
import type { PublicRoast } from '../services/submissionService'

// Plain-function wrapper: vi.fn's result recorder re-throws rejected promises as unhandled errors.
const impl = vi.hoisted(() => ({ get: (_slug: string): Promise<unknown> => Promise.resolve() }))
vi.mock('../services/submissionService', () => ({
  submissionService: { getPublicRoast: (slug: string) => impl.get(slug) },
}))

const getSpy = vi.fn()

const XSS = '<img src=x onerror=alert(1)>'

const roast: PublicRoast = {
  title: 'Spaghetti Special',
  roast_text: XSS,
  one_liner: 'Tests? Never heard of them.',
  fixes: ['Add tests', 'Write a README'],
  share_slug: 'slug123',
  created_at: '2026-01-01T00:00:00Z',
  score: 64,
  categories: {
    structure: 80,
    readme: 60,
    code_quality: 70,
    tests: 20,
    git_hygiene: 90,
    security: 85,
    originality: 50,
  },
  owner: 'octocat',
  repo: 'hello',
}

function renderPage() {
  return render(
    <ChakraProvider value={defaultSystem}>
      <MemoryRouter initialEntries={['/r/slug123']}>
        <Routes>
          <Route path="/r/:slug" element={<PublicRoastPage />} />
        </Routes>
      </MemoryRouter>
    </ChakraProvider>,
  )
}

describe('PublicRoastPage', () => {
  beforeEach(() => {
    getSpy.mockReset()
    impl.get = (slug) => getSpy(slug) as Promise<unknown>
  })

  it('renders the roast, escapes its text, and requests the slug from the URL', async () => {
    getSpy.mockResolvedValue(roast)
    const { container } = renderPage()
    expect(await screen.findByText('octocat/hello')).toBeInTheDocument()
    expect(screen.getByText('Spaghetti Special')).toBeInTheDocument()
    expect(screen.getByText('Add tests')).toBeInTheDocument()
    expect(screen.getByText(XSS)).toBeInTheDocument()
    expect(container.querySelector('img[src="x"]')).toBeNull()
    expect(screen.getByRole('img', { name: /Score 64/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /roast your own repo/i })).toBeInTheDocument()
    expect(getSpy).toHaveBeenCalledWith('slug123')
  })

  it('marks the page noindex', async () => {
    getSpy.mockResolvedValue(roast)
    renderPage()
    await screen.findByText('Spaghetti Special')
    const meta = document.querySelector('meta[name="robots"]')
    expect(meta).not.toBeNull()
    expect(meta?.getAttribute('content')).toBe('noindex')
  })

  it('shows a private/missing message on 404 and no roast content', async () => {
    impl.get = async () => {
      throw new Error('Roast not found')
    }
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent(/private or does not exist/i)
    expect(screen.queryByText('Spaghetti Special')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /roast your own repo/i })).not.toBeInTheDocument()
  })

  it('shows a loading state before the roast arrives', () => {
    getSpy.mockReturnValue(new Promise(() => undefined))
    renderPage()
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })

  it('omits the score section when the roast has no score', async () => {
    getSpy.mockResolvedValue({
      ...roast,
      score: null,
      categories: null,
    })
    renderPage()
    await screen.findByText('Spaghetti Special')
    expect(screen.queryByRole('img', { name: /Score/ })).not.toBeInTheDocument()
  })
})
