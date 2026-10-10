import { Field, Heading, Input, Stack, Text } from '@chakra-ui/react'
import { useState, type FormEvent } from 'react'
import { NavBar } from '../components/layout/NavBar'
import { PageWrapper } from '../components/layout/PageWrapper'
import { PrimaryButton } from '../components/ui/PrimaryButton'
import { Panel } from '../components/ui/Panel'
import { useAuth } from '../hooks/useAuth'
import { getErrorMessage, updateMe } from '../services/authService'

export default function ProfilePage() {
  const { user, setUser } = useAuth()
  const [fullName, setFullName] = useState(user?.full_name ?? '')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setMessage(null)
    setError(null)
    setSaving(true)
    try {
      setUser(await updateMe({ full_name: fullName.trim() }))
      setMessage('Profile updated')
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Could not update profile'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <PageWrapper>
      <NavBar />
      <Panel maxW="md" mx="auto" mt="10">
        <Heading size="xl" mb="4">
          Profile
        </Heading>
        <form onSubmit={onSubmit}>
          <Stack gap="4">
            <Field.Root>
              <Field.Label>Email</Field.Label>
              <Input value={user?.email ?? ''} readOnly />
            </Field.Root>
            <Field.Root>
              <Field.Label>Full name</Field.Label>
              <Input value={fullName} onChange={(e) => setFullName(e.target.value)} />
            </Field.Root>
            {message && <Text color="fg">{message}</Text>}
            {error && (
              <Text color="gold.fg" fontWeight="semibold" role="alert">
                {error}
              </Text>
            )}
            <PrimaryButton type="submit" disabled={saving}>
              {saving ? 'Saving...' : 'Save'}
            </PrimaryButton>
          </Stack>
        </form>
      </Panel>
    </PageWrapper>
  )
}
