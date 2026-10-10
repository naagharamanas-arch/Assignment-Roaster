import { Box, Button, Heading, Stack, Text } from '@chakra-ui/react'
import { useEffect, useState } from 'react'
import { Link as RouterLink, useParams } from 'react-router-dom'
import { PageWrapper } from '../components/layout/PageWrapper'
import { CategoryBars } from '../components/submission/CategoryBars'
import { FixesList } from '../components/submission/FixesList'
import { RoastCard } from '../components/submission/RoastCard'
import { ScoreRing } from '../components/submission/ScoreRing'
import { Panel } from '../components/ui/Panel'
import { submissionService, type PublicRoast } from '../services/submissionService'

export function PublicRoastPage() {
  const { slug } = useParams<{ slug: string }>()
  const [roast, setRoast] = useState<PublicRoast | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!slug) return
    let cancelled = false
    submissionService
      .getPublicRoast(slug)
      .then((r) => { if (!cancelled) setRoast(r) })
      .catch(() => { if (!cancelled) setError('This roast is private or does not exist.') })
    return () => { cancelled = true }
  }, [slug])

  return (
    <PageWrapper>
      <meta name="robots" content="noindex" />
      <Box maxW="3xl" mx="auto" mt="6">
        {error && (
          <Panel>
            <Text role="alert">{error}</Text>
          </Panel>
        )}
        {!error && !roast && <Panel><Text>Loading…</Text></Panel>}
        {roast && (
          <Stack gap="6">
            {roast.owner && roast.repo && <Heading size="xl">{roast.owner}/{roast.repo}</Heading>}
            {typeof roast.score === 'number' && (
              <Panel>
                <Stack align="center" gap="4">
                  <ScoreRing score={roast.score} />
                  {roast.categories && <CategoryBars categories={roast.categories} />}
                </Stack>
              </Panel>
            )}
            <RoastCard title={roast.title} oneLiner={roast.one_liner} text={roast.roast_text} />
            <FixesList fixes={roast.fixes} />
            <Button asChild alignSelf="center"><RouterLink to="/">Roast your own repo</RouterLink></Button>
          </Stack>
        )}
      </Box>
    </PageWrapper>
  )
}

export default PublicRoastPage
