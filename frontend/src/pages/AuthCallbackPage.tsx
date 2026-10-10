import { Text } from '@chakra-ui/react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Panel } from '../components/ui'
import { PageWrapper } from '../components/layout/PageWrapper'
import { storeTokens } from '../services/authService'

/** Receives Google OAuth tokens from the URL fragment, stores them, then reloads into the app. */
export default function AuthCallbackPage() {
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ''))
    const accessToken = params.get('access_token')
    const refreshToken = params.get('refresh_token')
    if (!accessToken || !refreshToken) {
      setFailed(true)
      return
    }
    storeTokens({ access_token: accessToken, refresh_token: refreshToken, token_type: 'bearer' })
    // Drop the tokens from the address bar and history, then reload so AuthContext picks them up.
    window.location.replace('/submit')
  }, [])

  return (
    <PageWrapper>
      <Panel>
        {failed ? (
          <Text role="alert">
            Google sign-in failed: we did not receive your session. <Link to="/login">Try again</Link>
          </Text>
        ) : (
          <Text>Signing you in…</Text>
        )}
      </Panel>
    </PageWrapper>
  )
}
