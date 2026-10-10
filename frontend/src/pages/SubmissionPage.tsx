import { Box, Button, Flex, Heading, HStack, SimpleGrid, Stack, Text } from '@chakra-ui/react'
import { useState } from 'react'
import { Link as RouterLink, useParams } from 'react-router-dom'
import { PageWrapper } from '../components/layout/PageWrapper'
import { CategoryBars } from '../components/submission/CategoryBars'
import { FixesList } from '../components/submission/FixesList'
import { LANGUAGE_STYLES, OptionGroup, ROAST_LEVELS } from '../components/submission/OptionGroup'
import { ProgressSteps } from '../components/submission/ProgressSteps'
import { RoastCard } from '../components/submission/RoastCard'
import { ScoreRing } from '../components/submission/ScoreRing'
import { Panel } from '../components/ui/Panel'
import { useSubmissionPolling, POLL_INTERVAL_MS, POLL_MAX_MS } from '../hooks/useSubmissionPolling'
import { submissionService } from '../services/submissionService'
import type { LanguageStyle, RoastLevel, Submission } from '../types'

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

function Result({ submission, onUpdate }: { submission: Submission; onUpdate: (s: Submission) => void }) {
  const { analysis, roast } = submission
  const [level, setLevel] = useState<RoastLevel>(submission.roast_level)
  const [style, setStyle] = useState<LanguageStyle>(submission.language_style)
  const [notice, setNotice] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const shareUrl = roast ? `${window.location.origin}/r/${roast.share_slug}` : ''

  async function handleCopyRoast() {
    if (!roast) return
    setNotice((await copyText(roast.roast_text)) ? 'Roast copied!' : 'Copy failed.')
  }

  async function handleCopyLink() {
    setNotice((await copyText(shareUrl)) ? 'Link copied!' : 'Copy failed.')
  }

  async function handleRegenerate() {
    setBusy(true)
    setActionError(null)
    try {
      onUpdate(await submissionService.regenerate(submission.id, { roast_level: level, language_style: style }))
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Regenerate failed.')
    } finally {
      setBusy(false)
    }
  }

  async function handleToggleShare() {
    if (!roast) return
    setBusy(true)
    setActionError(null)
    try {
      const updated = await submissionService.setVisibility(roast.id, !roast.is_public)
      onUpdate({ ...submission, roast: { ...roast, ...updated } })
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not update sharing.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Stack gap="6">
      <Heading size="xl">{submission.owner}/{submission.repo}</Heading>
      {analysis && (
        <SimpleGrid columns={{ base: 1, md: 2 }} gap="6">
          <Panel>
            <Flex direction="column" align="center" gap="3">
              <ScoreRing score={analysis.score} />
              <Text color="fg.muted">Overall score</Text>
            </Flex>
          </Panel>
          <Panel>
            <Heading size="md" mb="3">Categories</Heading>
            <CategoryBars categories={analysis.categories} />
          </Panel>
        </SimpleGrid>
      )}
      {roast && <RoastCard title={roast.title} oneLiner={roast.one_liner} text={roast.roast_text} />}
      {roast && <FixesList fixes={roast.fixes} />}
      {analysis && (
        <SimpleGrid columns={{ base: 1, md: 2 }} gap="6">
          <Panel>
            <Heading size="md" mb="3">Strengths</Heading>
            <Stack as="ul" gap="2" ps="5">
              {analysis.strengths.map((s, i) => <li key={`${i}-${s}`}>{s}</li>)}
            </Stack>
          </Panel>
          <Panel>
            <Heading size="md" mb="3">Issues</Heading>
            <Stack as="ul" gap="2" ps="5">
              {analysis.issues.map((issue, i) => (
                <li key={`${i}-${issue.file ?? 'general'}`}>
                  {issue.file && <strong>{issue.file} </strong>}({issue.severity}): {issue.problem}
                </li>
              ))}
            </Stack>
          </Panel>
        </SimpleGrid>
      )}
      {roast && (
        <Panel>
          <Stack gap="4">
            <HStack wrap="wrap" gap="3">
              <Button onClick={() => void handleCopyRoast()} variant="outline">Copy roast</Button>
              <Button onClick={() => void handleToggleShare()} disabled={busy} variant="outline" colorPalette="gold">
                {roast.is_public ? 'Make private' : 'Make public'}
              </Button>
              {roast.is_public && <Button onClick={() => void handleCopyLink()} variant="outline">Copy link</Button>}
            </HStack>
            {roast.is_public && <Text fontSize="sm" color="fg.muted" wordBreak="break-all">{shareUrl}</Text>}
            <Heading size="sm">Regenerate with a different level or style</Heading>
            <OptionGroup legend="Roast level" options={ROAST_LEVELS} value={level} onChange={setLevel} />
            <OptionGroup legend="Language style" options={LANGUAGE_STYLES} value={style} onChange={setStyle} />
            <Box>
              <Button onClick={() => void handleRegenerate()} disabled={busy} colorPalette="gold">Regenerate</Button>
            </Box>
            {notice && <Text role="status" color="fg">{notice}</Text>}
            {actionError && <Text role="alert" color="gold.fg" fontWeight="semibold">{actionError}</Text>}
          </Stack>
        </Panel>
      )}
    </Stack>
  )
}

export function SubmissionPage({
  pollMs = POLL_INTERVAL_MS,
  maxPollMs = POLL_MAX_MS,
}: {
  pollMs?: number
  maxPollMs?: number
}) {
  const { id } = useParams<{ id: string }>()
  const { submission, error, timedOut, setSubmission, restart } = useSubmissionPolling(id, pollMs, maxPollMs)

  function handleUpdate(next: Submission) {
    setSubmission(next)
    restart()
  }

  let body
  if (error && !submission) {
    body = (
      <Panel>
        <Text role="alert" color="gold.fg" fontWeight="semibold">{error}</Text>
        <Button mt="4" onClick={restart}>Retry</Button>
      </Panel>
    )
  } else if (!submission) {
    body = <Panel><Text>Loadingâ€¦</Text></Panel>
  } else if (submission.status === 'failed') {
    body = (
      <Panel>
        <Heading size="lg">Roast failed</Heading>
        <Text role="alert" mt="2" color="gold.fg" fontWeight="semibold">{submission.error ?? 'Something went wrong while processing this repo.'}</Text>
        <HStack mt="4" gap="3">
          <Button asChild><RouterLink to="/submit">Try again</RouterLink></Button>
          <Button asChild variant="outline"><RouterLink to="/history">Back to history</RouterLink></Button>
        </HStack>
      </Panel>
    )
  } else if (submission.status === 'done') {
    body = <Result submission={submission} onUpdate={handleUpdate} />
  } else {
    body = (
      <Panel>
        <Heading size="lg" mb="4">Roasting {submission.owner}/{submission.repo}</Heading>
        <ProgressSteps status={submission.status} />
        {timedOut && (
          <Box mt="4">
            <Text role="status" fontWeight="semibold">
              This is taking longer than expected. It may still finish in the background.
            </Text>
            <Button mt="3" variant="outline" onClick={restart}>Refresh</Button>
          </Box>
        )}
      </Panel>
    )
  }

  return (
    <PageWrapper>
      <Box maxW="4xl" mx="auto" mt="6">
        {error && submission && <Text role="alert" color="gold.fg" fontWeight="semibold" mb="3">{error}</Text>}
        {body}
      </Box>
    </PageWrapper>
  )
}

export default SubmissionPage

