# KapexAI Deployment Guide

This guide covers deploying the KapexAI application for **free** using:
- **Frontend**: Vercel (free tier)
- **Backend**: Railway (free tier - $5/month credit)
- **Worker**: Railway (same project, background worker)
- **Database**: Existing PostgreSQL (Prisma)
- **Redis**: Existing Redis Cloud (free tier)
- **CI/CD**: GitHub Actions (3 workflows)

> **Why Railway over Render?** Railway's free tier includes background workers that don't spin down, while Render's free background workers spin down after inactivity. Railway's $5/month credit covers both services easily.

---

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│    Backend       │────▶│   Redis Queue   │
│   (Vercel)      │     │  (Railway/Render)│     │  (Redis Cloud)  │
└─────────────────┘     └────────┬─────────┘     └────────┬────────┘
                                 │                      │
                                 ▼                      ▼
                        ┌──────────────────┐     ┌─────────────────┐
                        │   PostgreSQL     │     │    Worker       │
                        │   (Prisma/DB)    │     │  (Railway/Render)│
                        └──────────────────┘     └─────────────────┘
```

---

## Prerequisites

- GitHub account
- Vercel account
- Railway account (or Render)
- Redis Cloud account (already set up)
- PostgreSQL database (already set up)
- Google Cloud Console project (for OAuth)
- Mistral API key
- Tavily API key
- Indian Kanoon API token (optional)

---

## 1. Environment Variables

### Backend & Worker (`.env`)

```bash
# Database
DATABASE_URL="postgresql://user:password@host:5432/kapexai?sslmode=require"

# Redis
REDIS_URL="redis://user:password@host:port"

# Auth
JWT_SECRET="your-long-random-string-min-32-chars"
GOOGLE_CLIENT_ID="your-google-client-id.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET="your-google-client-secret"
GOOGLE_REDIRECT_URI="https://your-backend-domain.com/auth/google/callback"

# LLM / Tools
GOOGLE_API_KEY="your-google-api-key"
TAVILY_API_KEY="your-tavily-api-key"
INDIANKANOON_API_TOKEN="your-indian-kanoon-api-token"
SEC_USER_AGENT="KapexAI contact@yourdomain.com"

# Feedback → Google Sheets (optional, off by default)
FEEDBACK_ENABLED="false"
FEEDBACK_SPREADSHEET_ID="your-google-spreadsheet-id"
FEEDBACK_SHEET_NAME="Feedback"
# Use exactly one credential option — see "Feedback (optional)" below.
FEEDBACK_GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account", ...}'
```

### Feedback (optional)

Feedback is **off unless you turn it on**, and it needs no LLM key, no worker and
no database migration. To enable it, add the five variables above to the backend
service (not the worker) and restart it. Full detail, including the spreadsheet
headers, is in [`docs/feedback.md`](feedback.md); the deployment-specific points:

**1. Credentials — pick one option.**

| Option | Variable | When to use |
|---|---|---|
| Key file | `FEEDBACK_GOOGLE_APPLICATION_CREDENTIALS` | Only if you can mount a file into the container. The repo's `.dockerignore` keeps `*.env` and service-account JSON out of the build context, so a file present at build time will **not** be in the image — you must mount it at runtime. |
| Inline JSON | `FEEDBACK_GOOGLE_SERVICE_ACCOUNT_JSON` | **Recommended for deployment.** Paste the same key as a single-line JSON string. No file needs to exist in the image. |

Whichever you choose, mark it as a **secret** in your platform's variable
settings so it is not visible in build logs or to other services. The inline
JSON must keep its newlines escaped as `\n` inside `private_key`; a key pasted
with real newlines will not parse and the endpoint will return `503`.

**2. Google Cloud side.** The Sheets API must be enabled, and the service
account's `client_email` must be an **Editor** on the target spreadsheet —
otherwise every append fails with `403`.

**3. The spreadsheet and tab already exist.** Create the tab named in
`FEEDBACK_SHEET_NAME` and put the ten headers in row 1, columns A–J. The
deployment never creates the sheet or the tab, and never writes a header row.

**4. Frontend.** Nothing. The button appears based on the `feedback_enabled`
flag that `/auth/me` returns, and the frontend needs no credentials of any kind.

**5. `FeedbackDev` vs `Feedback`.** Both are tabs on the *same* spreadsheet, so
they are a way to keep test rows apart from real ones — **not** an access
boundary. Anything with Editor access can read both. Use a separate Google Cloud
project if you need real isolation.

**6. What to expect at runtime.** Appends are best-effort: one attempt, no
automatic retry, and an ambiguous result (`502 feedback_uncertain`) is surfaced
to the user as "this may already be saved, resending may duplicate it". If the
rate limiter cannot reach Redis the endpoint returns `503` and refuses the
write; no other route is affected.

### Frontend (`.env.local` → Vercel Environment Variables)

```bash
VITE_GOOGLE_CLIENT_ID="your-google-client-id.apps.googleusercontent.com"
VITE_API_BASE_URL="https://your-backend-domain.com"
```

---

## 2. Deploy Frontend to Vercel

### Option A: Via Vercel Dashboard (Recommended)

1. Push code to GitHub
2. Go to [Vercel Dashboard](https://vercel.com/dashboard)
3. Click **"Add New..."** → **"Project"**
4. Import your GitHub repository
5. Configure:
   - **Framework Preset**: Vite
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
   - **Install Command**: `npm install`
6. Add Environment Variables (from above)
7. Click **Deploy**

### Option B: Via Vercel CLI

```bash
cd frontend
npm install -g vercel
vercel login
vercel --prod
```

### Vercel Settings for SPA

The `vite.config.ts` already handles SPA fallback. For Vercel, add `vercel.json` in `frontend/`:

```json
{
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

---

## 3. Deploy Backend & Worker

### Option A: Railway (Recommended - Easier Free Tier)

Railway offers $5/month free credit (enough for small apps).

#### Setup

1. Go to [Railway](https://railway.app)
2. Sign up with GitHub
3. Click **"New Project"** → **"Deploy from GitHub repo"**
4. Select your repository
5. **Configure two services**:

#### Service 1: Backend

- **Name**: `kapex-backend`
- **Root Directory**: `/` (monorepo root)
- **Build Command**: `uv sync --all-packages && uv run prisma generate --schema=services/database/schema.prisma && uv run prisma py fetch`
- **Start Command**: `uv run --package backend uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- **Environment Variables**: Add all backend `.env` variables
- **Port**: Railway auto-assigns `$PORT`

#### Service 2: Worker

- **Name**: `kapex-worker`
- **Root Directory**: `/`
- **Build Command**: `uv sync --all-packages && uv run prisma generate --schema=services/database/schema.prisma && uv run prisma py fetch`
- **Start Command**: `uv run --package worker python -m worker.main`
- **Environment Variables**: Same as backend
- **No port needed** (background worker)

#### Railway Configuration Files

Create `railway.toml` in project root:

```toml
[build]
builder = "nixpacks"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 300
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3

[[services]]
name = "backend"
rootDirectory = "/"
buildCommand = "uv sync --all-packages && uv run prisma generate --schema=services/database/schema.prisma && uv run prisma py fetch"
startCommand = "uv run --package backend uvicorn backend.main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"

[[services]]
name = "worker"
rootDirectory = "/"
buildCommand = "uv sync --all-packages && uv run prisma generate --schema=services/database/schema.prisma && uv run prisma py fetch"
startCommand = "uv run --package worker python -m worker.main"
```

### Option B: Render (Alternative)

Render free tier: 750 hours/month, spins down after 15 min inactivity.

1. Go to [Render Dashboard](https://dashboard.render.com)
2. **New Web Service** (Backend):
   - **Build Command**: 
     ```bash
     pip install uv && uv sync --all-packages && uv run prisma generate --schema=services/database/schema.prisma && uv run prisma py fetch
     ```
   - **Start Command**: `uv run --package backend uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - **Environment**: Python 3.12+
   - **Root Directory**: Leave empty (repo root)
   - Add all env vars

3. **New Background Worker** (Worker):
   - **Build Command**: 
     ```bash
     pip install uv && uv sync --all-packages && uv run prisma generate --schema=services/database/schema.prisma && uv run prisma py fetch
     ```
   - **Start Command**: `uv run --package worker python -m worker.main`
   - **Root Directory**: Leave empty (repo root)
   - **Service Type**: Background Worker (not Web Service!)
   - Add same env vars

**Important**: 
- Render doesn't have `make` pre-installed. Use the direct `uv run prisma generate` command instead of `make generate`.
- **Must run `prisma py fetch`** after generate to download the query engine binary.
- **Worker must be a "Background Worker" service type**, not a "Web Service" (web services require port binding).

---

## 4. Update CORS & OAuth Redirects

### Backend CORS (backend/main.py)

Update `allow_origins` to include your Vercel domain:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://your-app.vercel.app",  # Add your Vercel URL
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Google OAuth Redirect URI

In Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client IDs:

- **Authorized JavaScript origins**: `https://your-app.vercel.app`
- **Authorized redirect URIs**: `https://your-backend-domain.com/auth/google/callback`

---

## 5. GitHub Actions Workflows

Create `.github/workflows/` directory with three workflow files.

### 5.1 Frontend Workflow (`.github/workflows/frontend.yml`)

**Manual only** — runs when you click "Run workflow" in GitHub Actions.

```yaml
name: Frontend CI/CD

on:
  workflow_dispatch:

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        run: cd frontend && npm ci

      - name: Type check and build
        run: cd frontend && npm run build

      - name: Install Vercel CLI
        run: npm install -g vercel@latest

      - name: Deploy to Vercel
        env:
          VERCEL_TOKEN: ${{ secrets.VERCEL_TOKEN }}
          VERCEL_ORG_ID: ${{ secrets.VERCEL_ORG_ID }}
          VERCEL_PROJECT_ID: ${{ secrets.VERCEL_PROJECT_ID }}
        run: |
          cd frontend
          vercel --prod --token=$VERCEL_TOKEN --scope=$VERCEL_ORG_ID --yes
```

### 5.2 Backend Workflow (`.github/workflows/backend.yml`)

**Manual only** — runs when you click "Run workflow" in GitHub Actions.

```yaml
name: Backend CI/CD

on:
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: ./
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "latest"

      - name: Set up Python
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync --all-packages

      - name: Generate Prisma client
        run: uv run prisma generate --schema=services/database/schema.prisma

      - name: Fetch Prisma query engine
        run: uv run prisma py fetch

      - name: Run tests
        run: .venv/bin/python -m pytest backend/tests/ -q
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          REDIS_URL: ${{ secrets.REDIS_URL }}
          JWT_SECRET: ${{ secrets.JWT_SECRET }}
          GOOGLE_CLIENT_ID: ${{ secrets.GOOGLE_CLIENT_ID }}
          GOOGLE_CLIENT_SECRET: ${{ secrets.GOOGLE_CLIENT_SECRET }}
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
          TAVILY_API_KEY: ${{ secrets.TAVILY_API_KEY }}

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Railway CLI
        run: npm install -g @railway/cli

      - name: Deploy to Railway
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
        run: |
          railway up --service kapex-backend --detach
```

### 5.3 Worker Workflow (`.github/workflows/worker.yml`)

**Manual only** — runs when you click "Run workflow" in GitHub Actions.

```yaml
name: Worker CI/CD

on:
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: ./
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "latest"

      - name: Set up Python
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync --all-packages

      - name: Generate Prisma client
        run: uv run prisma generate --schema=services/database/schema.prisma

      - name: Fetch Prisma query engine
        run: uv run prisma py fetch

      - name: Run worker tests
        run: PYTHONPATH=. uv run --package worker pytest worker/tests/ -v
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          REDIS_URL: ${{ secrets.REDIS_URL }}
          JWT_SECRET: ${{ secrets.JWT_SECRET }}
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
          TAVILY_API_KEY: ${{ secrets.TAVILY_API_KEY }}
          INDIANKANOON_API_TOKEN: ${{ secrets.INDIANKANOON_API_TOKEN }}

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to Railway
        uses: railwayapp/railway-deploy@v1
        with:
          token: ${{ secrets.RAILWAY_TOKEN }}
          service: kapex-worker
```

---

## 6. GitHub Secrets Configuration

Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

### Required Secrets

| Secret Name | Description |
|-------------|-------------|
| `VERCEL_TOKEN` | Vercel access token (from Vercel account settings) |
| `VERCEL_ORG_ID` | Vercel organization ID (`vercel inspect`) |
| `VERCEL_PROJECT_ID` | Vercel project ID (`vercel inspect`) |
| `RAILWAY_TOKEN` | Railway API token (from Railway account settings) |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis Cloud connection string |
| `JWT_SECRET` | Long random string (32+ chars) |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `GOOGLE_API_KEY` | Google Gemini API key |
| `TAVILY_API_KEY` | Tavily API key |
| `INDIANKANOON_API_TOKEN` | Indian Kanoon API token (optional) |

---

## 7. Database Migrations

Run migrations after deploying backend:

```bash
# Option 1: Railway CLI
railway login
railway link
railway run uv run prisma migrate deploy --schema=services/database/schema.prisma

# Option 2: Local with production DATABASE_URL
DATABASE_URL="your-production-url" uv run prisma migrate deploy --schema=services/database/schema.prisma
```

---

## 8. Verification Checklist

### Frontend (Vercel)
- [ ] Build succeeds
- [ ] Environment variables set
- [ ] Google OAuth works (popup sign-in)
- [ ] API calls reach backend
- [ ] WebSocket connects to backend

### Backend (Railway/Render)
- [ ] `/health` returns `{"status": "ok"}`
- [ ] Database connects (Prisma client generated)
- [ ] Redis connects
- [ ] CORS allows Vercel domain
- [ ] Google OAuth callback works
- [ ] JWT tokens issued/validated
- [ ] Feedback is **off by default**: `/auth/me` reports `feedback_enabled: false` and the Feedback button is hidden
- [ ] Only if feedback is enabled: one row appears in the target tab, with the ten A–J headers intact, `status = new`, and `contact_email` empty unless consent was ticked. Do not send a second submission just to observe the `429` — the cooldown and duplicate-row guards are covered by the automated tests (see [`docs/feedback.md`](feedback.md))

### Worker (Railway/Render)
- [ ] Starts without errors
- [ ] Connects to Redis queue
- [ ] Processes jobs from `jobs:queue`
- [ ] Publishes to `stream:{session_id}` channels
- [ ] Prisma client works

### Integration
- [ ] Frontend → Backend REST API works
- [ ] Frontend → Backend WebSocket works
- [ ] Backend → Redis queue works
- [ ] Worker → Redis queue consumes jobs
- [ ] Worker → Database saves messages
- [ ] Worker → Redis pub/sub streams to frontend

---

## 9. Free Tier Limits & Workarounds

| Service | Free Limit | Workaround |
|---------|------------|------------|
| Vercel | 100GB bandwidth, unlimited personal | Use for frontend only |
| Railway | $5/month credit (~500h) | Spin down when not needed |
| Render | 750h/month, spins down after 15min | Use cron job to ping `/health` |
| Redis Cloud | 30MB, 30 connections | Sufficient for dev/small scale |
| PostgreSQL (Neon/Supabase) | 0.5-1GB | Use free tier PostgreSQL providers |

### Keep-Alive for Render (if using)

Add to `worker/main.py` or separate cron job:

```python
# Ping backend every 10 minutes to prevent spin-down
import httpx
async def keep_alive():
    async with httpx.AsyncClient() as client:
        await client.get("https://your-backend.onrender.com/health")
```

Or use external cron (cron-job.org, GitHub Actions scheduled workflow).

---

## 10. Troubleshooting

### Common Issues

**Prisma client not found in production**
```bash
# Ensure generate runs in build
make generate
# Or in Dockerfile/CI: uv run prisma generate --schema=services/database/schema.prisma
```

**WebSocket connection fails**
- Check CORS allows Vercel domain
- Verify `VITE_API_BASE_URL` uses `wss://` for WebSocket
- Ensure backend `ws/session/{id}` endpoint accessible

**Worker not processing jobs**
- Check Redis connection (`REDIS_URL`)
- Verify `jobs:queue` has messages (`redis-cli LRANGE jobs:queue 0 -1`)
- Check worker logs for errors

**Feedback returns `503 feedback_disabled`**
- `FEEDBACK_ENABLED` is unset or not a truthy value (`true`/`1`/`yes`/`on`)
- Or the spreadsheet id, sheet name, or credential source is missing/unusable — a config problem is reported as "disabled" on purpose, so it can never break startup
- See [`docs/feedback.md`](feedback.md) for the full troubleshooting table

**Feedback returns `502` (failed or uncertain)**
- `failed`: the service account is probably not an Editor on the spreadsheet, or the inline JSON is malformed
- `uncertain`: Google timed out or returned `5xx`. **Check the sheet before the user resubmits** — the row may already be there and a retry would duplicate it. Appends are never retried automatically

**Google OAuth "redirect_uri_mismatch"**
- Exact match in Google Console: `https://your-backend.com/auth/google/callback`
- No trailing slashes

**CORS errors**
- Backend `allow_origins` must include `https://your-app.vercel.app`
- Credentials: `allow_credentials=True` requires specific origin (not `*`)

---

## 11. Cost Optimization Tips

1. **Railway**: Use `railway down` to stop services when not testing
2. **Render**: Services spin down automatically; accept cold starts
3. **Vercel**: Static frontend = nearly free
4. **Redis Cloud**: 30MB free tier sufficient for queue + pub/sub
5. **Database**: Use Neon/Supabase free PostgreSQL (0.5-1GB)

---

## 12. Next Steps

After initial deployment:
1. Set up custom domains (Vercel + Railway/Render)
2. Configure monitoring (Railway metrics, Vercel analytics)
3. Add error tracking (Sentry free tier)
4. Set up staging environment (separate branch/deployments)
5. Configure database backups

---

## Quick Reference Commands

```bash
# Local development
make install                    # uv sync
make generate                   # Prisma generate (local)
make migrate                    # Prisma migrate (local)
make dev-backend                # Backend on :8000
make dev-worker                 # Worker

# Direct Prisma commands (for CI/CD, Render, Railway)
uv run prisma generate --schema=services/database/schema.prisma
uv run prisma py fetch
uv run prisma migrate deploy --schema=services/database/schema.prisma

# Frontend
cd frontend && npm run dev      # :3000
cd frontend && npm run build    # Production build

# Deploy
vercel --prod                   # Frontend
railway up                      # Backend + Worker (if using Railway CLI)
```

---

## Support

- **Vercel Docs**: https://vercel.com/docs
- **Railway Docs**: https://docs.railway.app
- **Render Docs**: https://render.com/docs
- **Prisma Python**: https://prisma.io/docs/orm/overview/introduction
- **FastAPI**: https://fastapi.tiangolo.com