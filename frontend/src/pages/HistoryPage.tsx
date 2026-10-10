import { Badge, Box, Button, Flex, Heading, Stack, Text } from '@chakra-ui/react'
import { useCallback, useEffect, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import { PageWrapper } from '../components/layout/PageWrapper'
import { Panel } from '../components/ui/Panel'
import { submissionService } from '../services/submissionService'
import type { Submission, SubmissionStatus } from '../types'

const STATUS_COLOR: Record<SubmissionStatus, string> = {
  queued: 'gray',
  fetching: 'gold',
  analysing: 'gold',
  roasting: 'gold',
  done: 'gold',
  failed: 'gray',
}

const PAGE_SIZE = 50

export function HistoryPage() {
  const [items, setItems] = useState<Submission[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)

  const load = useCallback(async () => {
    try {
      const page = await submissionService.list({ limit: PAGE_SIZE, offset: 0 })
      setItems(page)
      setHasMore(page.length >= PAGE_SIZE)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load history.')
    }
  }, [])

  async function handleLoadMore() {
    if (!items) return
    setLoadingMore(true)
    try {
      const page = await submissionService.list({ limit: PAGE_SIZE, offset: items.length })
      setItems((prev) => [...(prev ?? []), ...page])
      setHasMore(page.length >= PAGE_SIZE)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load more.')
    } finally {
      setLoadingMore(false)
    }
  }

  useEffect(() => {
    void load()
  }, [load])

  async function handleDelete(id: number) {
    try {
      await submissionService.remove(id)
      setItems((prev) => (prev ? prev.filter((s) => s.id !== id) : prev))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed.')
    }
  }

  return (
    <PageWrapper>
      <Box maxW="3xl" mx="auto" mt="6">
        <Heading size="xl" mb="5">History</Heading>
        {error && <Text role="alert" color="gold.fg" fontWeight="semibold" mb="3">{error}</Text>}
        {items === null && !error && <Text>Loadingâ€¦</Text>}
        {items !== null && items.length === 0 && (
          <Panel>
            <Text>No roasts yet.</Text>
            <Button asChild mt="3"><RouterLink to="/submit">Roast a repo</RouterLink></Button>
          </Panel>
        )}
        <Stack gap="4">
          {items?.map((s) => (
            <Panel key={s.id}>
              <Flex justify="space-between" align="center" wrap="wrap" gap="3">
                <Box>
                  <RouterLink to={`/submissions/${s.id}`}>
                    <Text fontWeight="bold">{s.owner}/{s.repo}</Text>
                  </RouterLink>
                  <Text fontSize="sm" color="fg.muted">{new Date(s.created_at).toLocaleString()}</Text>
                </Box>
                <Flex align="center" gap="3">
                  {(s.score ?? s.analysis?.score) != null && (
                    <Text fontWeight="bold" aria-label="score">{s.score ?? s.analysis?.score}</Text>
                  )}
                  <Badge colorPalette={STATUS_COLOR[s.status]}>{s.status}</Badge>
                  <Button size="sm" variant="outline" colorPalette="gray" onClick={() => void handleDelete(s.id)} aria-label={`Delete ${s.owner}/${s.repo}`}>
                    Delete
                  </Button>
                </Flex>
              </Flex>
            </Panel>
          ))}
        </Stack>
        {hasMore && (
          <Button mt="4" variant="outline" onClick={() => void handleLoadMore()} disabled={loadingMore}>
            {loadingMore ? 'Loading…' : 'Load more'}
          </Button>
        )}
      </Box>
    </PageWrapper>
  )
}

export default HistoryPage

