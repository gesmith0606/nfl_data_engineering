# Deployment Guide

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Node.js | 20+ | Frontend build |
| Python | 3.9+ | Backend API |
| Docker | 24+ | Local dev / container builds |
| Vercel CLI | 37+ | Frontend deployment (optional; git integration is primary) |

## Local Development

### Parquet-only (no database required)

```bash
# Terminal 1: Backend
source venv/bin/activate
./web/run_dev.sh
# Or directly:
# uvicorn web.api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Frontend
cd web/frontend
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

The API reads from `data/gold/projections/` and `data/gold/predictions/` when `DATABASE_URL` is not set.

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- API docs: http://localhost:8000/api/docs

### With PostgreSQL (Docker Compose)

```bash
# Start PostgreSQL + API (schema auto-applied on first start)
docker compose up postgres api

# Load data
export DATABASE_URL=postgresql://nfl:nfl_local_2026@localhost:5432/nfl_data
python web/db/load_data.py --season 2024 --week 17

# In another terminal
cd web/frontend && npm run dev
```

### Full Docker Compose Stack

```bash
docker compose up          # postgres + api + neo4j
cd web/frontend && npm run dev   # frontend runs on host
```

---

## Production Deployment

### Frontend — Vercel (git integration)

The Vercel `frontend` project is connected to this GitHub repo with **Root Directory** = `web/frontend`. Every push to `main` triggers a Vercel build automatically — no CLI tokens, no manual GHA deploy step.

**Environment variable** (set once in Vercel dashboard under Project > Settings > Environment Variables):

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_API_URL` | `https://gesmith0606-nfl-data-api.hf.space` |

**Sentinel gate** (`.github/workflows/deploy-web.yml`, `deploy-frontend` job): after each push, CI polls `https://frontend-jet-seven-33.vercel.app/api/version` until the live `commit` field equals the pushed SHA (or a descendant). It hard-fails after ~10 minutes. The route reports `VERCEL_GIT_COMMIT_SHA`, so CLI deploys show `unknown` and will NOT satisfy the gate — always deploy via git push.

### Backend — Hugging Face Spaces

Production backend: **https://gesmith0606-nfl-data-api.hf.space**

The Space shallow-clones this public repo at build time and runs in Parquet-fallback mode (no live database). See `deploy/huggingface/README.md` for the full rebuild procedure — that file is the source of truth.

**Data refresh** is handled by the `deploy-backend` job in `.github/workflows/deploy-web.yml`:
1. Clones the HF Space repo (contains only a `Dockerfile` and `README.md`)
2. Bumps the `ARG CACHE_BUST=<date>-<run-number>` line in the Dockerfile
3. Commits and pushes, which triggers a HF Space rebuild
4. Calls the HF factory-rebuild API (`POST .../restart?factory=true`) as a belt-and-suspenders measure (HF does not reliably rebuild on push alone)
5. Also syncs `ANTHROPIC_API_KEY` to HF runtime secrets if the GH secret is set

The job requires `HF_TOKEN` in GitHub Secrets. If the token is missing, the refresh is skipped with a warning (non-blocking) and the bridge keeps serving its previous build.

**Manual fallback**: bump `CACHE_BUST` directly in https://huggingface.co/spaces/gesmith0606/nfl-data-api.

**Note (TD-09):** Any `data/` path the Dockerfile COPYs must have a matching `!data/.../**/*.parquet` allowlist in `.gitignore` and be committed to git. An uncommitted path causes builds to silently serve a stale image.

### Deploy gate (SANITY-M6)

`.github/workflows/deploy-web.yml` runs data quality checks before and after deploy:

1. **Pre-deploy quality gate** (`quality-gate` job): runs `scripts/sanity_check_projections.py --scoring half_ppr --season 2026`. Exit code 1 on CRITICAL issues blocks both deploy jobs.
2. **Weekly partition gate** (same job, `--check-weekly` flag): validates the weekly Gold Parquet the website's weekly view serves. A missing partition is a SKIP (API falls back to preseason); a present-but-stale or garbage partition blocks deploy.
3. **Live gate** (`live-gate-blocking` job, runs after both deploys): probes the live backend and frontend with `--check-live`. Non-zero exit fails the workflow and triggers auto-rollback.
4. **Auto-rollback** (`auto-rollback` job): if the live gate fails within 5 minutes of deploy, performs a `git revert` and pushes to `main`. Never force-pushes; branch protection rules still apply.

### GitHub Actions Secrets

| Secret | Description |
|--------|-------------|
| `HF_TOKEN` | Hugging Face token — needed for Space refresh and secret sync |
| `ANTHROPIC_API_KEY` | Synced to HF runtime; enables sentiment extraction |

### Verification

After deploying, verify each component:

```bash
# Backend health
curl https://gesmith0606-nfl-data-api.hf.space/api/health
# Expected: {"status":"ok","version":"0.1.0","db_status":"parquet_fallback"}

# Backend version
curl https://gesmith0606-nfl-data-api.hf.space/api/version
# Expected: JSON with git_sha, build_date, etc.

# Frontend
# Visit https://frontend-jet-seven-33.vercel.app and confirm pages load:
#   /              -- Home page
#   /projections   -- Fantasy projections
#   /predictions   -- Game predictions

# Backend data (via API)
curl "https://gesmith0606-nfl-data-api.hf.space/api/projections?season=2026&scoring=half_ppr"
# Expected: JSON array of player projections
```

### Architecture (current)

```
Vercel (Next.js)  -->  HF Spaces (FastAPI, Parquet-fallback)
                            |
                       Parquet files baked into the Space image
                       at build time via repo shallow-clone
```

---

## Environment Variables Reference

| Variable | Where | Required | Default | Description |
|----------|-------|----------|---------|-------------|
| `DATABASE_URL` | Backend | No | (none) | PostgreSQL connection string; omit for Parquet fallback |
| `CORS_ORIGINS` | Backend | No | `localhost:3000,localhost:8000` | Comma-separated allowed origins |
| `NFL_DATA_DIR` | Backend | No | `<project_root>/data` | Base data directory for Parquet reads |
| `API_KEY` | Backend | No | (none) | Enables X-API-Key auth middleware when set; health/docs/openapi paths exempt |
| `NEXT_PUBLIC_API_URL` | Frontend | Yes | `http://localhost:8000` | Backend API base URL |

---

## Legacy / Historical Deployment Paths

The sections below describe infrastructure that is no longer in use. They are retained for reference only.

### Railway (DEAD — trial expired May 2026)

> Railway is not a current or alternative deployment path. The trial expired in May 2026 and the old URL (`nfldataengineering-production.up.railway.app`) 404s on every route. The auto-rollback job comment referencing Railway is stale; rollback pushes to `main` and the HF Space rebuild is triggered on the next `deploy-web` run.

Railway previously deployed automatically from the `web/Dockerfile` on push to `main`. No action is needed unless a paid Railway plan is reinstated.

### Render (Deprecated)

> Render was evaluated as an alternative to Railway but was never used in production.

To deploy on Render: connect the GitHub repo, set Dockerfile path to `web/Dockerfile`, and add `DATABASE_URL` and `CORS_ORIGINS` environment variables.

### AWS SAM (Serverless Lambda)

> Not used in production. Retained as an option if a serverless AWS path is ever pursued.

```bash
pip install aws-sam-cli
cd web/api/serverless
sam build
sam deploy --guided
```

Guided prompts: stack name `nfl-data-api`, region `us-east-2`, parameter `CorsOrigins` = Vercel frontend URL.

Subsequent deploys (non-guided):

```bash
sam deploy \
  --stack-name nfl-data-api \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    DatabaseUrl="postgresql://..." \
    CorsOrigins="https://your-app.vercel.app" \
  --no-confirm-changeset
```

### Docker on ECR + ECS/Fargate

> Not used in production. Retained as an option if a container-on-AWS path is ever pursued.

```bash
# Create ECR repository (one-time)
aws ecr create-repository --repository-name nfl-data-api --region us-east-2

# Build and push
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI=$ACCOUNT_ID.dkr.ecr.us-east-2.amazonaws.com/nfl-data-api

aws ecr get-login-password --region us-east-2 | \
  docker login --username AWS --password-stdin $ECR_URI

docker build -f web/Dockerfile -t nfl-data-api .
docker tag nfl-data-api:latest $ECR_URI:latest
docker push $ECR_URI:latest
```

Then create an ECS Fargate service pointing to this image with environment variables:
- `CORS_ORIGINS` = Vercel frontend URL
- `DATABASE_URL` = PostgreSQL connection string (optional; omit for Parquet fallback)

### Supabase (PostgreSQL)

> Not used in production (Parquet-fallback mode is active on HF Spaces). Retained for any future database-backed deployment.

1. Create a project at https://supabase.com
2. Run `web/db/schema.sql` in the SQL editor
3. Copy the connection string from Settings > Database > Connection string (URI)
4. Load data:

```bash
export DATABASE_URL="postgresql://postgres:[password]@db.[ref].supabase.co:5432/postgres"
python web/db/load_data.py --season 2024 --week 17
```

5. Set `DATABASE_URL` in the backend environment.
