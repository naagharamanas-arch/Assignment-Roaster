# Assignment Roaster

Paste a public GitHub repo URL. An AI reviews the assignment and roasts it in **Tamil**, then gives you a score and a short list of real fixes.

The roast targets the work, never the person. Every roast points at actual findings (missing tests, an empty README, a file name) and ends with actionable fixes in plain English.

## How it works

```
GitHub URL ─▶ validate (github.com only) ─▶ fetch snapshot via GitHub REST API
          ─▶ OpenAI analysis (strict JSON: score, 7 category scores, issues, strengths)
          ─▶ moderation ─▶ OpenAI roast (Tamil script or Tanglish, mild/medium/savage)
          ─▶ result page + optional public share link
```

- The repo is **never cloned or executed**. Only `api.github.com` is contacted, using up to 25 source files within 150 KB.
- Repo content is treated as untrusted. The roast step only ever sees the structured analysis, not raw repo text.
- Roasts are moderated before saving. If moderation blocks one twice, a plain, non-roast feedback summary is shown instead.

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, Python 3.12+, SQLAlchemy 2, Alembic |
| Database | PostgreSQL (psycopg 3) |
| Frontend | React 19, Vite, TypeScript (strict), Chakra UI v3 |
| Auth | JWT with rotating refresh tokens, email/password, Google OAuth |
| AI | OpenAI API (structured outputs + moderation) |
| Infra | Docker, docker-compose, GitHub Actions |

## Quick start (Docker)

```bash
cp .env.example .env
# edit .env: set SECRET_KEY, OPENAI_API_KEY, OPENAI_MODEL, GITHUB_TOKEN (see below)
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000 (health: `/health`, API docs: `/docs`)

`docker-compose.dev.yml` adds hot reload. Run it with
`docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build`.

## Local development (without Docker)

```bash
# Backend (needs a running PostgreSQL)
cd backend
python -m venv .venv && .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload                        # http://localhost:8000

# Frontend
cd frontend
npm install
npm run dev                                          # http://localhost:3000
```

The backend reads `.env` from `backend/` or the repo root.

## Configuration

Copy `.env.example` to `.env`. The important variables:

| Variable | Purpose |
|----------|---------|
| `ENVIRONMENT` | `development` allows a placeholder secret. Any other value (compose defaults to `production`) refuses to start unless `SECRET_KEY` is random and 32+ characters. |
| `SECRET_KEY` | JWT signing key. Generate with `openssl rand -hex 32`. |
| `DATABASE_URL` | Postgres URL. A plain `postgresql://` URL is mapped to the psycopg 3 driver. |
| `OPENAI_API_KEY` | Server-side only. |
| `OPENAI_MODEL` | Model for analysis and roast, for example `gpt-4o-mini`. Check the Tamil output before choosing a smaller model. |
| `GITHUB_TOKEN` | Strongly recommended. Without it GitHub allows only 60 requests/hour per IP, roughly 2 roasts an hour for the whole server. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Optional, for Google sign-in. Set the redirect URI to `<API_BASE_URL>/api/v1/auth/google/callback`. |
| `API_BASE_URL` / `APP_BASE_URL` | Public URLs of the backend and frontend. |
| `FORWARDED_ALLOW_IPS` | IP(s) of your reverse proxy, so rate limits see real client IPs. |

Never commit `.env`. It is git-ignored.

### Limits and cost controls

- 3 roasts per user per day, enforced atomically in SQL
- 1 submission per repo per user per hour
- A global daily job cap (`GLOBAL_DAILY_JOB_CAP`, default 200) returns 503 when reached
- Token caps on every OpenAI call, a pipeline timeout, and a concurrency limit
- Analyses are cached by `(owner, repo, commit_sha, brief)`
- A background reaper fails and refunds jobs stuck after a restart

## API overview

All routes are under `/api/v1`.

| Area | Endpoints |
|------|-----------|
| Auth | `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `GET/PUT /auth/me`, `GET /auth/google`, `/auth/google/callback` |
| Submissions | `POST /submissions`, `GET /submissions`, `GET/DELETE /submissions/{id}`, `GET /submissions/{id}/analysis`, `POST /submissions/{id}/roast/regenerate` |
| Roasts | `GET /roasts/{share_slug}` (public, only if shared), `PUT /roasts/{id}/visibility` |

Interactive docs are at `/docs` while the backend is running.

## Testing

```bash
# Backend: 168 tests, ~95% coverage. OpenAI and GitHub are always mocked.
cd backend && pytest --cov=app --cov-fail-under=80
ruff check . && mypy app

# Frontend: 62 tests
cd frontend && npm test && npm run type-check && npm run lint && npm run build
```

CI (`.github/workflows/ci.yml`) runs lint, mypy, migrations against a real Postgres, tests, dependency audits, and a Docker build.

## Project structure

```
backend/
  app/
    routers/      auth, submissions, roasts
    services/     github_client, jobs, usage_service, openai_analyzer, roast_writer, moderation, auth_service
    prompts/      analysis.md, roast_tamil.md
    models/       SQLAlchemy models
    schemas/      Pydantic schemas (pipeline.py is the shared contract)
  alembic/        migrations
  tests/
frontend/
  src/            pages, components, services, hooks, context, theme.ts
INITIAL.md        product definition
PRPs/             implementation blueprint
CLAUDE.md         project rules for Claude Code
```

## Design

The UI uses exactly two colours, midnight ink and champagne gold, defined in `frontend/src/theme.ts`. No gradients. Use theme tokens rather than hard-coded colours.

## Known limitations

- Background jobs run inside the web process. Move to a real queue (RQ or arq with Redis) before running multiple instances or if jobs must survive deploys.
- The refresh-token reuse grace window is held in process memory, so it does not work across multiple backend workers.
- The rate limiter uses in-memory storage. Use Redis for production.
- `frontend/nginx.conf` ships a Content-Security-Policy that allows `http://localhost:8000` as the API origin. Change it for your domain.
- Billing (Dodo Payments), the admin panel and a leaderboard are planned but not built.
- Tamil roast quality depends on the model. Review sample output per level before launch.

## Built with the MicroSaaS template

This repo started from a Claude Code MicroSaaS template. The `.claude/commands`, `agents/` and `skills/` folders are from it: `/setup-project`, `/generate-prp` and `/execute-prp` generated `INITIAL.md`, the PRP and the first build.
