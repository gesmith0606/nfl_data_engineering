# Deployment Guide

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Node.js | 20+ | Frontend build |
| Python | 3.9+ | Backend API |
| Docker | 24+ | Container builds (optional) |
| AWS CLI | 2.x | Backend deployment |
| AWS SAM CLI | 1.x | Serverless deployment |
| Vercel CLI | 37+ | Frontend deployment (optional) |

## Local Development

### Parquet-only (no database required)

```bash
# Terminal 1: Backend
source venv/bin/activate
./web/run_dev.sh
# Or directly:
# uvicorn web.api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Frontend
cd web/frontend && npm run dev
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

## Production Deployment

### Frontend (Vercel)

#### Option A: Vercel CLI

```bash
# One-time setup
npm i -g vercel
cd web/frontend
vercel login
vercel link   # Follow prompts to create/link a Vercel project

# Deploy
vercel --prod
```

#### Option B: Vercel Dashboard (Recommended)

1. Go to https://vercel.com/new
2. Import the GitHub repository
3. Set **Root Directory** to `web/frontend`
4. Framework preset will auto-detect Next.js
5. Add environment variables (see below)
6. Deploy

#### Option C: GitHub Actions (CI/CD)

Pushes to `main` that touch `web/frontend/` auto-deploy via `.github/workflows/deploy-web.yml`.

**Required GitHub Secrets:**

| Secret | Description |
|--------|-------------|
| `VERCEL_TOKEN` | Personal access token from https://vercel.com/account/tokens |
| `VERCEL_ORG_ID` | From `.vercel/project.json` after `vercel link` |
| `VERCEL_PROJECT_ID` | From `.vercel/project.json` after `vercel link` |
| `API_URL` | Production API URL (e.g., `https://api.yourdomain.com`) |

#### Vercel Environment Variables

Set these in the Vercel dashboard under Project > Settings > Environment Variables:

| Variable | Value | Notes |
|----------|-------|-------|
| `NEXT_PUBLIC_API_URL` | `https://your-api-domain.com` | Points to deployed backend |

### Backend (AWS)

#### Option A: AWS SAM (Serverless Lambda)

```bash
# Install SAM CLI if needed
pip install aws-sam-cli

# Build and deploy
cd web/api/serverless
sam build
sam deploy --guided
```

Follow the guided prompts:
- Stack name: `nfl-data-api`
- Region: `us-east-2`
- Parameter `DatabaseUrl`: your Supabase connection string
- Parameter `CorsOrigins`: your Vercel frontend URL
- Allow SAM to create IAM roles: Yes

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

#### Option B: Docker on ECR + ECS/Fargate

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
- `DATABASE_URL` = Supabase connection string
- `CORS_ORIGINS` = Vercel frontend URL

#### Option C: Railway / Render (Simplest)

1. Connect your GitHub repository
2. Set the Dockerfile path to `web/Dockerfile`
3. Add `DATABASE_URL` and `CORS_ORIGINS` environment variables
4. Deploy

#### GitHub Actions CI/CD

Pushes to `main` auto-deploy via `.github/workflows/deploy-web.yml`.

**Required GitHub Secrets:**

| Secret | Description |
|--------|-------------|
| `AWS_ACCESS_KEY_ID` | IAM access key |
| `AWS_SECRET_ACCESS_KEY` | IAM secret key |
| `DATABASE_URL` | Supabase PostgreSQL connection string |
| `CORS_ORIGINS` | Frontend URL (e.g., `https://your-app.vercel.app`) |

### Database (Supabase)

1. Create a project at https://supabase.com
2. Go to SQL Editor and run the contents of `web/db/schema.sql`
3. Copy the connection string from Settings > Database > Connection string (URI)
4. Load data:

```bash
export DATABASE_URL="postgresql://postgres:[password]@db.[ref].supabase.co:5432/postgres"
python web/db/load_data.py --season 2024 --week 17
```

5. Set `DATABASE_URL` in your backend environment (SAM parameter, ECS env var, or Railway/Render dashboard)

## Environment Variables Reference

| Variable | Where | Required | Default | Description |
|----------|-------|----------|---------|-------------|
| `DATABASE_URL` | Backend | No | (none) | PostgreSQL connection string; omit for Parquet fallback |
| `CORS_ORIGINS` | Backend | No | `localhost:3000,localhost:8000` | Comma-separated allowed origins |
| `NFL_DATA_DIR` | Backend | No | `<project_root>/data` | Base data directory for Parquet reads |
| `NEXT_PUBLIC_API_URL` | Frontend | Yes | `http://localhost:8000` | Backend API base URL |

## Verification

After deploying, verify each component:

```bash
# Backend health check
curl https://your-api-domain.com/api/health
# Expected: {"status":"ok","version":"0.1.0","db_status":"connected"}

# Frontend
# Visit https://your-app.vercel.app and confirm pages load:
#   /              -- Home page
#   /projections   -- Fantasy projections
#   /predictions   -- Game predictions

# Database (via API)
curl "https://your-api-domain.com/api/projections?season=2024&week=17&scoring=half_ppr"
# Expected: JSON array of player projections
```

## Architecture

```
Vercel (Next.js)  -->  AWS Lambda / Docker (FastAPI)  -->  Supabase (PostgreSQL)
                                                       \-> Parquet files (fallback)
```

The API uses a dual-source pattern: it reads from PostgreSQL when `DATABASE_URL` is set, and falls back to reading Parquet files from the local `data/` directory when it is not. This means the backend works immediately in local development with zero database setup.
