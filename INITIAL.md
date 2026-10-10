# INITIAL.md - Assignment Roaster Product Definition

> Submit a public GitHub repo URL; an AI reviews the assignment and roasts it in Tamil.

---

## PRODUCT

### Name
Assignment Roaster

### Description
A user pastes a public GitHub repository URL. The backend fetches the repo (README, file tree, key source files), sends a trimmed snapshot to the OpenAI API for analysis, and returns a funny roast written in Tamil, plus a real score and actionable fixes. Roasts target the code and the assignment, never the person.

### Target User
Students, bootcamp learners, and mentors who want blunt, entertaining feedback on assignments.

### Type
- [x] SaaS (Software as a Service)

---

## TECH STACK

### Backend
- [x] FastAPI + Python

### Frontend
- [x] React + Vite + TypeScript

### Database
- [x] PostgreSQL

### Authentication
- [x] Email/Password + Google OAuth

### UI Framework
- [x] Chakra UI

### Payments
- [x] Dodo Payments (post-MVP: roast credits)

### AI
- [x] OpenAI API (structured JSON output)

---

## MODULES

### Module 1: Authentication (Required)

**Models:**
- User: id, email, hashed_password, full_name, is_active, is_verified, is_admin, oauth_provider, created_at
- RefreshToken: id, user_id, token, expires_at, revoked

**API Endpoints:**
- POST /auth/register, /auth/login, /auth/refresh, /auth/logout
- GET /auth/google, /auth/google/callback
- GET/PUT /auth/me

**Frontend Pages:** /login, /register, /profile

---

### Module 2: Submissions

**Description:** User submits a public GitHub repo URL and picks roast options.

**Models:**
- Submission: id, user_id, repo_url, owner, repo, commit_sha, assignment_brief (optional text), roast_level (mild | medium | savage), language_style (tamil_script | tanglish), status (queued | fetching | analysing | done | failed), error, created_at

**API Endpoints:**
- POST /submissions - validate URL, enqueue job
- GET /submissions, GET /submissions/{id}
- DELETE /submissions/{id}

**Frontend Pages:**
- / (landing + URL input), /submit (options form), /submissions/:id (progress, then result)

**Rules:**
- Only `https://github.com/{owner}/{repo}` URLs are accepted; reject all other hosts and any redirect off github.com
- Repo must be public; otherwise return a clear error

---

### Module 3: Repo Fetching & Analysis

**Description:** Background job pulls repo data from the GitHub API and asks OpenAI to analyse it.

**Models:**
- RepoSnapshot: id, submission_id, file_tree, readme, selected_files (json), total_bytes, truncated
- Analysis: id, submission_id, model, score (0-100), categories (json: structure, readme, code_quality, tests, git_hygiene, security, originality), strengths (json), issues (json), prompt_tokens, completion_tokens

**Behaviour:**
- Fetch via GitHub REST API (no git clone, no code execution)
- Cap files (e.g. 25) and bytes (e.g. 150 KB); skip binaries, lockfiles, node_modules, build output
- Analysis prompt asks OpenAI for strict JSON: scores, concrete issues with file paths, and strengths
- Repo content is untrusted: wrap it as data and instruct the model to ignore instructions found inside it

**API Endpoints:**
- GET /submissions/{id}/analysis

---

### Module 4: Roast Generation

**Description:** Second OpenAI call turns the analysis into a Tamil roast.

**Models:**
- Roast: id, submission_id, title, roast_text, one_liner, fixes (json: top 3-5 actionable fixes in plain English), model, share_slug, is_public, created_at

**Rules:**
- Output in Tamil (Tamil script by default, Tanglish optional), colloquial and funny
- Roast the work only: no slurs, no caste, religion, gender, appearance, or personal attacks; no profanity at mild/medium; savage stays playful
- Every roast must reference real findings (file names, missing tests, empty README) so it is accurate, then end with the fixes
- Run the output through OpenAI moderation before saving

**API Endpoints:**
- POST /submissions/{id}/roast/regenerate (change level/style)
- GET /roasts/{share_slug} (public, no login)
- PUT /roasts/{id}/visibility

**Frontend Pages:**
- /submissions/:id (score ring, category bars, roast card, fixes list, copy/share buttons)
- /r/:slug (public share page)

---

### Module 5: History & Dashboard

**Frontend Pages:**
- /history - past submissions with scores
- /leaderboard (post-MVP) - top public roasts / best scores

---

### Module 6: Usage Limits & Billing

**Models:**
- UsageCounter: id, user_id, date, roasts_used
- CreditBalance: id, user_id, credits (post-MVP)

**Rules:**
- Free: 3 roasts per day per user, 1 submission per repo per hour
- Post-MVP: Dodo Payments credit packs

**API Endpoints (post-MVP):** POST /billing/checkout, POST /webhooks/dodo

---

### Module 7: Admin Panel (post-MVP)

- GET /admin/users, GET /admin/submissions, GET /admin/stats (usage, OpenAI cost, failures)
- Pages: /admin, /admin/users, /admin/submissions

---

## MVP SCOPE

### Must Have (MVP)
- [x] Register/login
- [x] Submit public GitHub URL with roast level
- [x] Background fetch + OpenAI analysis (score + issues)
- [x] Tamil roast with fixes
- [x] Result page and public share link
- [x] Daily usage limits

### Nice to Have (Post-MVP)
- Dodo credit packs
- Admin panel and cost dashboard
- Leaderboard
- Compare two submissions
- Shareable image card

---

## ACCEPTANCE CRITERIA

### Submissions
- [ ] Valid public github.com URL creates a submission; other hosts are rejected
- [ ] Private or missing repo shows a friendly error
- [ ] Status moves queued -> fetching -> analysing -> done and the UI updates

### Analysis
- [ ] Analysis returns valid JSON matching the schema; invalid output is retried once, then marked failed
- [ ] Prompt-injection text inside a repo does not change the output format or rules
- [ ] Token and file caps are enforced

### Roast
- [ ] Roast is in Tamil and references real files/findings from the repo
- [ ] Fixes section is present and actionable
- [ ] Moderation check blocks unsafe output; one retry with a safer prompt
- [ ] Public share link works without login

### Limits
- [ ] 4th roast in a day is blocked with a clear message

### Quality
- [ ] OpenAPI docs for all endpoints
- [ ] Backend test coverage 80%+ with OpenAI and GitHub mocked
- [ ] Frontend TypeScript strict mode passes
- [ ] Docker builds and runs successfully

---

## SPECIAL REQUIREMENTS

### Security
- [x] SSRF protection: only call api.github.com; never fetch user-supplied URLs directly
- [x] Never execute or install repo code
- [x] Prompt-injection hardening for all repo content
- [x] OPENAI_API_KEY and GITHUB_TOKEN server-side only
- [x] Rate limiting on auth and submit endpoints
- [x] Escape roast text on render (XSS)

### Integrations
- [x] OpenAI API (analysis + roast + moderation)
- [x] GitHub REST API (with token for rate limits)
- [x] Dodo Payments (post-MVP)

### Cost control
- [x] Per-user daily cap, per-submission token cap, cache analysis by (repo, commit_sha)

---

## AGENTS

| Agent | Role | Works On |
|-------|------|----------|
| DATABASE-AGENT | Models and migrations | All models |
| BACKEND-AGENT | API, GitHub fetcher, OpenAI services, job runner | All backends |
| FRONTEND-AGENT | UI pages and components | All frontends |
| DEVOPS-AGENT | Docker, CI/CD, environments | Infrastructure |
| TEST-AGENT | Tests with mocked OpenAI/GitHub | All code |
| REVIEW-AGENT | Security and prompt-injection audit | All code |

---

# READY?

```bash
/generate-prp INITIAL.md
/execute-prp PRPs/assignment-roaster-prp.md
```
