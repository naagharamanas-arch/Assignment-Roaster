import { Field, Input, Stack, Text } from '@chakra-ui/react'
import { useState, type FormEvent } from 'react'
import { Link as RouterLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import { getErrorMessage } from '../../services/authService'
import { PrimaryButton } from '../ui/PrimaryButton'
import { GoogleLoginButton } from './GoogleLoginButton'

interface RegisterErrors {
  email?: string
  password?: string
  confirm?: string
}

export function validateRegister(email: string, password: string, confirm: string): RegisterErrors {
  const errors: RegisterErrors = {}
  if (!/^\S+@\S+\.\S+$/.test(email)) errors.email = 'Enter a valid email address'
  if (password.length < 8) errors.password = 'Password must be at least 8 characters'
  if (confirm !== password) errors.confirm = 'Passwords do not match'
  return errors
}

export function RegisterForm() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [errors, setErrors] = useState<RegisterErrors>({})
  const [serverError, setServerError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setServerError(null)
    const found = validateRegister(email, password, confirm)
    setErrors(found)
    if (Object.keys(found).length > 0) return
    setSubmitting(true)
    try {
      await register(email, password, fullName.trim())
      navigate('/submit', { replace: true })
    } catch (err: unknown) {
      setServerError(getErrorMessage(err, 'Registration failed. Please try again.'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate>
      <Stack gap="4">
        <Field.Root>
          <Field.Label>Full name</Field.Label>
          <Input value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="name" />
        </Field.Root>
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
            autoComplete="new-password"
          />
          <Field.ErrorText>{errors.password}</Field.ErrorText>
        </Field.Root>
        <Field.Root invalid={Boolean(errors.confirm)}>
          <Field.Label>Confirm password</Field.Label>
          <Input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
          />
          <Field.ErrorText>{errors.confirm}</Field.ErrorText>
        </Field.Root>
        {serverError && (
          <Text color="gold.fg" fontWeight="semibold" role="alert">
            {serverError}
          </Text>
        )}
        <PrimaryButton type="submit" disabled={submitting}>
          {submitting ? 'Creating account...' : 'Create account'}
        </PrimaryButton>
        <GoogleLoginButton />
        <Text fontSize="sm">
          Already registered? <RouterLink to="/login">Sign in</RouterLink>
        </Text>
      </Stack>
    </form>
  )
}
