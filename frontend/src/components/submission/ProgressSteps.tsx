import { Badge, Flex, HStack, Text } from '@chakra-ui/react'
import type { SubmissionStatus } from '../../types'

export const PIPELINE_STEPS: { key: Exclude<SubmissionStatus, 'failed'>; label: string }[] = [
  { key: 'queued', label: 'Queued' },
  { key: 'fetching', label: 'Fetching repo' },
  { key: 'analysing', label: 'Analysing' },
  { key: 'roasting', label: 'Roasting' },
  { key: 'done', label: 'Done' },
]

export function ProgressSteps({ status }: { status: SubmissionStatus }) {
  const current = PIPELINE_STEPS.findIndex((s) => s.key === status)
  return (
    <Flex as="ol" direction="column" gap="2" listStyleType="none" p="0" aria-label="Progress">
      {PIPELINE_STEPS.map((step, i) => {
        const state = status === 'done' || i < current ? 'complete' : i === current ? 'current' : 'pending'
        return (
          <HStack as="li" key={step.key} data-state={state} gap="3">
            <Badge
              colorPalette={state === 'complete' ? 'gold' : state === 'current' ? 'gold' : 'gray'}
              variant={state === 'pending' ? 'outline' : 'solid'}
              rounded="full"
              px="2"
            >
              {state === 'complete' ? '✓' : i + 1}
            </Badge>
            <Text fontWeight={state === 'current' ? 'bold' : 'normal'} color={state === 'pending' ? 'fg.muted' : 'fg'}>
              {step.label}
              {state === 'current' && status !== 'done' ? '…' : ''}
            </Text>
          </HStack>
        )
      })}
    </Flex>
  )
}
