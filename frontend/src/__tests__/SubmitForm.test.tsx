import { ChakraProvider, defaultSystem } from '@chakra-ui/react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SubmitForm } from '../components/submission/SubmitForm'
import type { Submission } from '../types'

// Route calls through a plain function so rejections are not tracked by the vi.fn result recorder.
const impl = vi.hoisted(() => ({ create: (_payload: unknown): Promise<unknown> => Promise.resolve() }))
vi.mock('../services/submissionService', () => ({
  submissionService: { create: (payload: unknown) => impl.create(payload) },
}))

const createSpy = vi.fn()

function renderForm() {
  return render(
    <ChakraProvider value={defaultSystem}>
      <MemoryRouter initialEntries={['/submit']}>
        <Routes>
          <Route path="/submit" element={<SubmitForm />} />
          <Route path="/submissions/:id" element={<div>detail page</div>} />
        </Routes>
      </MemoryRouter>
    </ChakraProvider>,
  )
}

const created = { id: 42 } as Submission

describe('SubmitForm', () => {
  beforeEach(() => {
    createSpy.mockReset()
    impl.create = (payload) => createSpy(payload) as Promise<unknown>
  })

  it('defaults to medium / tanglish', () => {
    renderForm()
    expect(screen.getByRole('radio', { name: 'Medium' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: 'Tanglish' })).toHaveAttribute('aria-checked', 'true')
  })

  it('sends the selected level, style, trimmed url and brief, then navigates', async () => {
    createSpy.mockResolvedValue(created)
    renderForm()
    await userEvent.type(
      screen.getByLabelText(/github repository url/i),
      '  https://github.com/octocat/hello/  ',
    )
    await userEvent.click(screen.getByRole('radio', { name: 'Savage' }))
    await userEvent.click(screen.getByRole('radio', { name: /Tamil script/ }))
    await userEvent.type(screen.getByLabelText(/assignment brief/i), '  Build a todo app  ')
    await userEvent.click(screen.getByRole('button', { name: /roast my repo/i }))

    expect(createSpy).toHaveBeenCalledWith({
      repo_url: 'https://github.com/octocat/hello',
      roast_level: 'savage',
      language_style: 'tamil_script',
      assignment_brief: 'Build a todo app',
    })
    expect(await screen.findByText('detail page')).toBeInTheDocument()
  })

  it('omits assignment_brief when blank', async () => {
    createSpy.mockResolvedValue(created)
    renderForm()
    await userEvent.type(
      screen.getByLabelText(/github repository url/i),
      'https://github.com/octocat/hello',
    )
    await userEvent.click(screen.getByRole('radio', { name: 'Mild' }))
    await userEvent.click(screen.getByRole('button', { name: /roast my repo/i }))
    const payload = createSpy.mock.calls[0][0] as Record<string, unknown>
    expect(payload).toEqual({
      repo_url: 'https://github.com/octocat/hello',
      roast_level: 'mild',
      language_style: 'tanglish',
    })
    expect('assignment_brief' in payload).toBe(false)
  })

  it('rejects non-GitHub URLs without calling the service', async () => {
    renderForm()
    await userEvent.type(screen.getByLabelText(/github repository url/i), 'https://evil.com/a/b')
    await userEvent.click(screen.getByRole('button', { name: /roast my repo/i }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(createSpy).not.toHaveBeenCalled()
  })

  it('shows the service error and stays on the form', async () => {
    impl.create = async () => {
      throw new Error('Daily limit reached')
    }
    renderForm()
    await userEvent.type(
      screen.getByLabelText(/github repository url/i),
      'https://github.com/octocat/hello',
    )
    await userEvent.click(screen.getByRole('button', { name: /roast my repo/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Daily limit reached')
    expect(screen.queryByText('detail page')).not.toBeInTheDocument()
  })
})
