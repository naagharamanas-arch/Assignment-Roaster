import { Heading } from '@chakra-ui/react'
import { RegisterForm } from '../components/auth/RegisterForm'
import { NavBar } from '../components/layout/NavBar'
import { PageWrapper } from '../components/layout/PageWrapper'
import { Panel } from '../components/ui/Panel'

export default function RegisterPage() {
  return (
    <PageWrapper>
      <NavBar />
      <Panel maxW="md" mx="auto" mt="10">
        <Heading size="xl" mb="4">
          Register
        </Heading>
        <RegisterForm />
      </Panel>
    </PageWrapper>
  )
}
