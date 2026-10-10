import { Field, Input, Stack, Text } from '@chakra-ui/react'
import { useState, type FormEvent } from 'react'
import { Link as RouterLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import { getErrorMessage } from '../../services/authService'
import { PrimaryButton } from '../ui/PrimaryButton'
import { GoogleLoginButton } from './GoogleLoginButton'

interface LoginErrors {
  email?: string
  password?: string
}

export function validateLogin(email: string, password: string): LoginErrors {
  const errors: LoginErrors = {}
  if (!/^\S+@\S+\.\S+$/.test(email)) errors.email = 'Enter a valid email address'
  if (password.length < 8) errors.password = 'Password must be at least 8 characters'
  return errors
}

interface LocationState {
  from?: string
}

export function LoginForm() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<LoginErrors>({})
  const [serverError, setServerError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setServerError(null)
    const found = validateLogin(email, password)
    setErrors(found)
    if (Object.keys(found).length > 0) return
    setSubmitting(true)
    try {
      await login(email, password)
      const from = (location.state as LocationState | null)?.from
      navigate(from ?? '/submit', { replace: true })
    } catch (err: unknown) {
      setServerError(getErrorMessage(err, 'Login failed. Check your credentials.'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate>
      <Stack gap="4">
        <Field.Root invalid={Boolean(errors.email)}>
          <Field.Label>Email</Field.Label>
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
          <Field.ErrorText>{errors.email}</Field.ErrorText>
        </Field.Root>
        <Field.Root invalid={Boolean(errors.password)}>
          <Field.Label>Password</Field.Label>
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
          <Field.ErrorText>{errors.password}</Field.ErrorText>
        </Field.Root>
        {serverError && (
          <Text color="gold.fg" fontWeight="semibold" role="alert">
            {serverError}
          </Text>
        )}
        <PrimaryButton type="submit" disabled={submitting}>
          {submitting ? 'Signing in...' : 'Sign in'}
        </PrimaryButton>
        <GoogleLoginButton />
        <Text fontSize="sm">
          No account? <RouterLink to="/register">Register</RouterLink>
        </Text>
      </Stack>
    </form>
  )
}
