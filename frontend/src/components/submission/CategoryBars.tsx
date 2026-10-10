import { Box, Flex, Stack, Text } from '@chakra-ui/react'
import type { CategoryScores } from '../../types'

const LABELS: Record<keyof CategoryScores, string> = {
  structure: 'Structure',
  readme: 'README',
  code_quality: 'Code quality',
  tests: 'Tests',
  git_hygiene: 'Git hygiene',
  security: 'Security',
  originality: 'Originality',
}

export function CategoryBars({ categories }: { categories: CategoryScores }) {
  const keys = Object.keys(LABELS) as (keyof CategoryScores)[]
  return (
    <Stack gap="3" w="full">
      {keys.map((key) => {
        const value = Math.max(0, Math.min(100, categories[key] ?? 0))
        return (
          <Box key={key}>
            <Flex justify="space-between" mb="1">
              <Text fontSize="sm">{LABELS[key]}</Text>
              <Text fontSize="sm" fontWeight="semibold">{value}</Text>
            </Flex>
            <Box
              h="2"
              rounded="full"
              bg="bg.emphasized"
              role="progressbar"
              aria-label={LABELS[key]}
              aria-valuenow={value}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <Box h="full" rounded="full" bg="gold.500" w={`${value}%`} />
            </Box>
          </Box>
        )
      })}
    </Stack>
  )
}
