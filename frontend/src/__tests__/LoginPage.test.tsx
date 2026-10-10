import { ChakraProvider, defaultSystem } from '@chakra-ui/react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import LoginPage from '../pages/LoginPage'

vi.mock('../components/auth/LoginForm', () => ({ LoginForm: () => <div>form</div> }))
vi.mock('../components/layout/NavBar', () => ({ NavBar: () => null }))

function renderAt(url: string) {
  return render(
    <ChakraProvider value={defaultSystem}>
      <MemoryRouter initialEntries={[url]}>
        <LoginPage />
      </MemoryRouter>
    </ChakraProvider>,
  )
}

describe('LoginPage oauth errors', () => {
  it('shows a friendly message for ?error=', () => {
    renderAt('/login?error=oauth_state')
    expect(screen.getByRole('alert')).toHaveTextContent(/expired or was invalid/i)
  })

  it('shows nothing without an error code', () => {
    renderAt('/login')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
