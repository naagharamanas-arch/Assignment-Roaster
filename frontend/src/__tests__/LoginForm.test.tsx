import { ChakraProvider, defaultSystem } from '@chakra-ui/react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { LoginForm, validateLogin } from '../components/auth/LoginForm'
import { AuthContext, type AuthContextValue } from '../context/AuthContext'

const login = vi.fn<AuthContextValue['login']>().mockResolvedValue(undefined)
const ctx: AuthContextValue = {
  user: null,
  loading: false,
  login,
  register: vi.fn(),
  logout: vi.fn(),
  setUser: vi.fn(),
}

function renderForm() {
  return render(
    <ChakraProvider value={defaultSystem}>
      <AuthContext.Provider value={ctx}>
        <MemoryRouter>
          <LoginForm />
        </MemoryRouter>
      </AuthContext.Provider>
    </ChakraProvider>,
  )
}

describe('validateLogin', () => {
  it('flags bad email and short password', () => {
    expect(validateLogin('nope', 'short')).toEqual({
      email: 'Enter a valid email address',
      password: 'Password must be at least 8 characters',
    })
  })
  it('passes valid input', () => {
    expect(validateLogin('a@b.co', 'longenough')).toEqual({})
  })
})

describe('LoginForm', () => {
  it('shows validation errors and does not submit', async () => {
    renderForm()
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Enter a valid email address')).toBeInTheDocument()
    expect(screen.getByText('Password must be at least 8 characters')).toBeInTheDocument()
    expect(login).not.toHaveBeenCalled()
  })

  it('submits valid credentials', async () => {
    renderForm()
    await userEvent.type(screen.getByLabelText('Email'), 'a@b.co')
    await userEvent.type(screen.getByLabelText('Password'), 'longenough')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(login).toHaveBeenCalledWith('a@b.co', 'longenough')
  })
})
