# PRP: Assignment Roaster

> Implementation blueprint for parallel agent execution

---

## METADATA

| Field | Value |
|-------|-------|
| **Product** | Assignment Roaster |
| **Type** | SaaS |
| **Version** | 1.0 |
| **Created** | 2026-10-10 |
| **Complexity** | Medium-High (LLM pipeline, untrusted input, cost control) |

---

## PRODUCT OVERVIEW

**Description:** User submits a public GitHub repo URL. The backend fetches a trimmed snapshot via the GitHub API, OpenAI analyses it into a structured score and issue list, and a second OpenAI call writes a funny Tamil roast with actionable fixes.

**Value Proposition:** Blunt, entertaining, and genuinely useful assignment feedback in seconds, in a language learners enjoy.

**MVP Scope:**
- [ ] Register/login
- [ ] Submit public GitHub URL with roast level
- [ ] Background fetch + OpenAI analysis (score, issues)
- [ ] Tamil roast with fixes
- [ ] Result page and public share link
- [ ] Daily usage limits

**Post-MVP:** Dodo credit packs, admin panel and cost dashboard, leaderboard, compare submissions, share image card.

---

## TECH STACK

| Layer | Technology | Skill Reference |
|-------|------------|-----------------|
| Backend | FastAPI + Python 3.11+ | skills/BACKEND.md |
| Frontend | React + TypeScript + Vite | skills/FRONTEND.md |
| Database | PostgreSQL + SQLAlchemy + Alembic | skills/DATABASE.md |
| Auth | JWT + bcrypt + Google OAuth | skills/BACKEND.md |
| UI | Chakra UI | skills/FRONTEND.md |
| AI | OpenAI API (JSON schema output, moderation) | skills/BACKEND.md |
| Source data | GitHub REST API | skills/BACKEND.md |
| Jobs | FastAPI BackgroundTasks first; Celery/RQ if load needs it | skills/BACKEND.md |
| Testing | pytest + RTL, OpenAI/GitHub mocked | skills/TESTING.md |
| Deployment | Docker + GitHub Actions | skills/DEPLOYMENT.md |

---

## DATABASE MODELS

| Model | Key fields |
|-------|-----------|
| User | id, email, hashed_password, full_name, is_active, is_verified, is_admin, oauth_provider, created_at |
| RefreshToken | id, user_id, token, expires_at, revoked |
| Submission | id, user_id, repo_url, owner, repo, commit_sha, assignment_brief, roast_level, language_style, status, error, created_at |
| RepoSnapshot | id, submission_id, file_tree, readme, selected_files, total_bytes, truncated |
| Analysis | id, submission_id, model, score, categories, strengths, issues, prompt_tokens, completion_tokens |
| Roast | id, submission_id, title, roast_text, one_liner, fixes, model, share_slug, is_public, created_at |
| UsageCounter | id, user_id, date, roasts_used (unique user_id+date) |
| CreditBalance (post-MVP) | id, user_id, credits |

Indexes: Submission(user_id, created_at), Submission(owner, repo, commit_sha), Roast(share_slug unique).

---

## MODULES

### Module 1: Authentication
**Agents:** DATABASE + BACKEND + FRONTEND

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/v1/auth/register, /login, /refresh, /logout | Email/password |
| GET | /api/v1/auth/google, /google/callback | Google OAuth (verify state) |
| GET/PUT | /api/v1/auth/me | Profile |

Pages: /login, /register, /profile.

### Module 2: Submissions
**Agents:** BACKEND + FRONTEND

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /submissions | Validate github.com URL, check daily limit, enqueue job |
| GET | /submissions | List mine |
| GET | /submissions/{id} | Status + result |
| DELETE | /submissions/{id} | Delete |

Pages: `/` (landing + URL input), `/submit` (options), `/submissions/:id` (progress -> result, polling every 2s).

### Module 3: Repo Fetching & Analysis
**Agents:** BACKEND

Pipeline (`services/jobs.py`): queued -> fetching -> analysing -> roasting -> done | failed.
- `github_client`: resolve default branch + commit SHA, file tree, README, pick up to 25 source files within 150 KB; skip binaries, lockfiles, vendor/build dirs
- `openai_analyzer`: strict JSON `{score, categories{structure, readme, code_quality, tests, git_hygiene, security, originality}, strengths[], issues[{file, problem, severity}]}`; Pydantic validation; one retry
- Cache by (owner, repo, commit_sha) to avoid repeat spend

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /submissions/{id}/analysis | Scores and issues |

### Module 4: Roast Generation
**Agents:** BACKEND + FRONTEND

- `roast_writer`: second call using `prompts/roast_tamil.md` with the analysis JSON (not raw repo content) as input; level mild/medium/savage; Tamil script or Tanglish
- Moderation check before save; one retry with a safer prompt, then fall back to a plain (non-roast) feedback summary
- Always append 3-5 actionable fixes in plain English

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /submissions/{id}/roast/regenerate | New level/style (counts toward limit) |
| GET | /roasts/{share_slug} | Public, no login |
| PUT | /roasts/{id}/visibility | Toggle public sharing |

Pages: result view (score ring, category bars, roast card, fixes, copy/share), `/r/:slug` public page with noindex meta by default.

### Module 5: History & Dashboard
Pages: /history. Post-MVP: /leaderboard.

### Module 6: Usage Limits & Billing
- MVP: UsageCounter, 3 roasts/day/user, 1 submission/repo/hour, 429 with reset time
- Post-MVP: Dodo checkout, verified idempotent webhook, credit balance

### Module 7: Admin Panel (post-MVP)
Endpoints: /admin/users, /admin/submissions, /admin/stats (usage, OpenAI cost, failures). Pages: /admin/*.

---

## PHASE EXECUTION PLAN

**Phase 1: Foundation (4 agents in parallel)**
- DATABASE-AGENT: models, migrations
- BACKEND-AGENT: app skeleton, config, GitHub client, OpenAI client wrapper, prompts folder
- FRONTEND-AGENT: Vite + Chakra setup, routing, auth context, API client
- DEVOPS-AGENT: Dockerfiles, docker-compose (api, web, postgres), CI, .env.example

**Validation Gate 1:** pip install, alembic upgrade head, npm install, docker-compose config

**Phase 2: Modules (backend + frontend parallel per module)**
- Auth -> Submissions -> Analysis pipeline -> Roast generation -> History/limits
- Post-MVP: Billing, Admin, Leaderboard

**Validation Gate 2:** ruff check, mypy, npm lint, npm type-check

**Phase 3: Quality (3 agents in parallel)**
- TEST-AGENT: pytest + RTL, 80%+ coverage; fixtures for GitHub and OpenAI responses; injection and invalid-JSON cases
- REVIEW-AGENT: SSRF, prompt injection, XSS in roast render, rate limits, secrets, cost caps
- RESEARCH-AGENT: confirm current OpenAI structured-output and moderation API usage and GitHub rate limits

**Final Validation:** full test suite, docker build, health checks

---

## VALIDATION GATES

| Gate | Commands |
|------|----------|
| 1 | `alembic upgrade head`, `npm install`, `docker-compose config` |
| 2 | `ruff check backend/`, `npm run type-check` |
| 3 | `pytest --cov --cov-fail-under=80`, `npm test` |
| Final | `docker-compose up -d`, `curl localhost:8000/health` |

---

## RISKS

- **Prompt injection from repo content:** delimit as data, analyse first and feed only the analysis JSON to the roast step.
- **Unsafe or offensive roast:** prompt rules plus moderation, with a plain-feedback fallback.
- **Tamil quality:** keep prompt examples of the desired tone; review sample outputs per level before launch.
- **Cost abuse:** per-user caps, token limits, commit-SHA cache, auth required.
- **GitHub rate limits:** use a server token; surface a friendly retry message.

---

## ENVIRONMENT VARIABLES

```env
DATABASE_URL=postgresql://user:password@localhost:5432/assignment_roaster
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-secret
OPENAI_API_KEY=
OPENAI_MODEL=
GITHUB_TOKEN=
DODO_API_KEY=
DODO_WEBHOOK_SECRET=
APP_BASE_URL=http://localhost:5173
VITE_API_URL=http://localhost:8000
```

---

## NEXT STEP

/execute-prp PRPs/assignment-roaster-prp.md
