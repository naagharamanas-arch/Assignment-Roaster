import { chakra, Input, Stack, Text, Textarea } from '@chakra-ui/react'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { validateGithubUrl } from '../../lib/github'
import { submissionService } from '../../services/submissionService'
import type { LanguageStyle, RoastLevel } from '../../types'
import { PrimaryButton } from '../ui/PrimaryButton'
import { LANGUAGE_STYLES, OptionGroup, ROAST_LEVELS } from './OptionGroup'

const BRIEF_MAX = 2000

export function SubmitForm() {
  const navigate = useNavigate()
  const [url, setUrl] = useState('')
  const [level, setLevel] = useState<RoastLevel>('medium')
  const [style, setStyle] = useState<LanguageStyle>('tanglish')
  const [brief, setBrief] = useState('')
  const [urlError, setUrlError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setSubmitError(null)
    const result = validateGithubUrl(url)
    if (!result.valid) {
      setUrlError(result.error)
      return
    }
    setUrlError(null)
    setLoading(true)
    try {
      const trimmedBrief = brief.trim()
      const created = await submissionService.create({
        repo_url: url.trim().replace(/\/$/, ''),
        roast_level: level,
        language_style: style,
        ...(trimmedBrief ? { assignment_brief: trimmedBrief } : {}),
      })
      navigate(`/submissions/${created.id}`)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Submission failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={(e) => void handleSubmit(e)} noValidate aria-label="Submit a repository">
      <Stack gap="5">
        <Stack gap="1">
          <chakra.label htmlFor="repo-url" fontWeight="semibold" fontSize="sm">GitHub repository URL</chakra.label>
          <Input
            id="repo-url"
            type="url"
            placeholder="https://github.com/owner/repo"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            aria-invalid={urlError !== null}
            aria-describedby={urlError ? 'repo-url-error' : undefined}
          />
          {urlError && <Text id="repo-url-error" role="alert" color="gold.fg" fontWeight="semibold" fontSize="sm">{urlError}</Text>}
        </Stack>
        <OptionGroup legend="Roast level" options={ROAST_LEVELS} value={level} onChange={setLevel} />
        <OptionGroup legend="Language style" options={LANGUAGE_STYLES} value={style} onChange={setStyle} />
        <Stack gap="1">
          <chakra.label htmlFor="brief" fontWeight="semibold" fontSize="sm">Assignment brief (optional)</chakra.label>
          <Textarea
            id="brief"
            rows={4}
            maxLength={BRIEF_MAX}
            placeholder="Paste what the assignment asked for so the roast can check against it"
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
          />
        </Stack>
        {submitError && <Text role="alert" color="gold.fg" fontWeight="semibold">{submitError}</Text>}
        <PrimaryButton type="submit" disabled={loading}>
          {loading ? 'Submitting…' : 'Roast my repo'}
        </PrimaryButton>
      </Stack>
    </form>
  )
}

