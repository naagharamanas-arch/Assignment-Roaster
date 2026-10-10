import { describe, expect, it } from 'vitest'
import { validateGithubUrl } from '../lib/github'

describe('validateGithubUrl', () => {
  it.each([
    'https://github.com/octocat/hello-world',
    'https://github.com/octocat/hello-world/',
    'https://github.com/a/b.c_d',
  ])('accepts %s', (u) => {
    expect(validateGithubUrl(u).valid).toBe(true)
  })

  it.each([
    '',
    'http://github.com/o/r',
    'https://gitlab.com/o/r',
    'https://github.com/o',
    'https://github.com/o/r/tree/main',
    'https://github.com.evil.com/o/r',
    'https://evil.com/https://github.com/o/r',
    'https://github.com/o/..',
    'javascript:alert(1)',
  ])('rejects %j', (u) => {
    expect(validateGithubUrl(u).valid).toBe(false)
  })

  it('parses owner and repo', () => {
    const r = validateGithubUrl('  https://github.com/octocat/hello ')
    expect(r.owner).toBe('octocat')
    expect(r.repo).toBe('hello')
  })
})
