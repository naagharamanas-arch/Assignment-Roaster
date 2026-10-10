import { Heading, Text } from '@chakra-ui/react'
import { useSearchParams } from 'react-router-dom'
import { LoginForm } from '../components/auth/LoginForm'
import { NavBar } from '../components/layout/NavBar'
import { PageWrapper } from '../components/layout/PageWrapper'
import { Panel } from '../components/ui/Panel'
import { oauthErrorMessage } from '../services/errors'

export default function LoginPage() {
  const [params] = useSearchParams()
  const message = oauthErrorMessage(params.get('error'))
  return (
    <PageWrapper>
      <NavBar />
      <Panel maxW="md" mx="auto" mt="10">
        <Heading size="xl" mb="4">
          Login
        </Heading>
        {message && (
          <Text role="alert" color="gold.fg" fontWeight="semibold" mb="4">
            {message}
          </Text>
        )}
        <LoginForm />
      </Panel>
    </PageWrapper>
  )
}

