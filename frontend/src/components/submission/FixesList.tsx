import { Heading, List } from '@chakra-ui/react'
import { Panel } from '../ui/Panel'

export function FixesList({ fixes }: { fixes: string[] }) {
  if (fixes.length === 0) return null
  return (
    <Panel>
      <Heading size="md" mb="3">Fixes</Heading>
      <List.Root as="ol" gap="2" ps="5">
        {fixes.map((fix, i) => (
          <List.Item key={`${i}-${fix}`}>{fix}</List.Item>
        ))}
      </List.Root>
    </Panel>
  )
}
