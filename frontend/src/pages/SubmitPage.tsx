import { Heading } from '@chakra-ui/react'
import { PageWrapper } from '../components/layout/PageWrapper'
import { SubmitForm } from '../components/submission/SubmitForm'
import { Panel } from '../components/ui/Panel'

export function SubmitPage() {
  return (
    <PageWrapper>
      <Panel maxW="2xl" mx="auto" mt="8">
        <Heading size="xl" mb="5">Submit a repo</Heading>
        <SubmitForm />
      </Panel>
    </PageWrapper>
  )
}

export default SubmitPage
