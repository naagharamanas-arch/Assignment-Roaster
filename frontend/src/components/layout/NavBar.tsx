import { Box, Button, Flex, Heading } from '@chakra-ui/react'
import { Link as RouterLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'

export function NavBar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function onLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <Flex as="nav" align="center" justify="space-between" px="6" py="3" gap="4" wrap="wrap">
      <Heading size="md" asChild>
        <RouterLink to="/">Assignment Roaster</RouterLink>
      </Heading>
      <Flex align="center" gap="3">
        <Button variant="ghost" asChild>
          <RouterLink to="/history">History</RouterLink>
        </Button>
        <Button variant="ghost" asChild>
          <RouterLink to="/submit">Submit</RouterLink>
        </Button>
        {user ? (
          <>
            <Button variant="ghost" asChild>
              <RouterLink to="/profile">Profile</RouterLink>
            </Button>
            <Button variant="outline" onClick={onLogout}>
              Logout
            </Button>
          </>
        ) : (
          <Box>
            <Button asChild>
              <RouterLink to="/login">Login</RouterLink>
            </Button>
          </Box>
        )}
      </Flex>
    </Flex>
  )
}
