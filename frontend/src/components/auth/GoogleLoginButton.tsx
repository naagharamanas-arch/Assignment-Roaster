import { Button } from '@chakra-ui/react'
import { googleLoginUrl } from '../../services/authService'

export function GoogleLoginButton() {
  return (
    <Button
      variant="outline"
      w="full"
      onClick={() => {
        window.location.assign(googleLoginUrl())
      }}
    >
      Continue with Google
    </Button>
  )
}
