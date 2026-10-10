import { Heading, Text } from '@chakra-ui/react'
import { PageWrapper } from '../components/layout/PageWrapper'
import { SubmitForm } from '../components/submission/SubmitForm'
import { Panel } from '../components/ui/Panel'

export function LandingPage() {
  return (
    <PageWrapper>
      <Heading as="h1" size="4xl" textAlign="center" mt="12">Assignment Roaster</Heading>
      <Text textAlign="center" fontSize="lg" color="fg.muted" mt="3" mb="8">
        Drop a public GitHub repo. Get a score, honest fixes, and a Tamil roast.
      </Text>
      <Panel maxW="2xl" mx="auto">
        <SubmitForm />
      </Panel>
    </PageWrapper>
  )
}

export default LandingPage
