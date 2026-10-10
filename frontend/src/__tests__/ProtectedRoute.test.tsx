import { ChakraProvider, defaultSystem } from '@chakra-ui/react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { ProtectedRoute } from '../components/auth/ProtectedRoute'
import { AuthContext, type AuthContextValue } from '../context/AuthContext'
import type { User } from '../types'

const user: User = {
  id: 1,
  email: 'a@b.co',
  full_name: null,
  is_active: true,
  is_verified: true,
  is_admin: false,
  oauth_provider: null,
  created_at: '2026-01-01T00:00:00Z',
}

function renderAt(value: Partial<AuthContextValue>) {
  const ctx: AuthContextValue = {
    user: null,
    loading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    setUser: vi.fn(),
    ...value,
  }
  return render(
    <ChakraProvider value={defaultSystem}>
      <AuthContext.Provider value={ctx}>
        <MemoryRouter initialEntries={['/secret']}>
          <Routes>
            <Route path="/login" element={<div>login page</div>} />
            <Route element={<ProtectedRoute />}>
              <Route path="/secret" element={<div>secret content</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>
    </ChakraProvider>,
  )
}

describe('ProtectedRoute', () => {
  it('redirects anonymous users to /login', () => {
    renderAt({})
    expect(screen.getByText('login page')).toBeInTheDocument()
    expect(screen.queryByText('secret content')).not.toBeInTheDocument()
  })
  it('renders children for authenticated users', () => {
    renderAt({ user })
    expect(screen.getByText('secret content')).toBeInTheDocument()
  })
})
