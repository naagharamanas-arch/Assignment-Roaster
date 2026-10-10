import { Heading, Text } from '@chakra-ui/react'
import { Panel } from '../ui/Panel'
import { TAMIL_FONT } from '../../lib/github'

interface RoastCardProps {
  title: string
  oneLiner?: string | null
  text: string
}

/** Roast content is untrusted: rendered strictly as text nodes (React escapes). */
export function RoastCard({ title, oneLiner, text }: RoastCardProps) {
  return (
    <Panel>
      <Heading size="lg" fontFamily={TAMIL_FONT}>{title}</Heading>
      {oneLiner && (
        <Text mt="2" fontStyle="italic" color="fg.muted" fontFamily={TAMIL_FONT}>{oneLiner}</Text>
      )}
      <Text mt="4" whiteSpace="pre-wrap" lineHeight="tall" fontFamily={TAMIL_FONT} data-testid="roast-text">
        {text}
      </Text>
    </Panel>
  )
}

