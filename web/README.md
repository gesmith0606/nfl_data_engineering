# NFL Data Engineering -- Web Platform

## Architecture

```
Next.js (Vercel)  -->  FastAPI (Lambda / Docker)  -->  PostgreSQL (Supabase)
                                                   \-> Parquet files (fallback)
```

- **Frontend**: Next.js app at `web/frontend/`, deployed to Vercel
- **Backend**: FastAPI app at `web/api/`, deployed to AWS Lambda (via Mangum) or Docker
- **Database**: PostgreSQL (Supabase in production, local via Docker Compose)
- **Fallback**: When `DATABASE_URL` is not set, the API reads directly from Parquet files

## Local Development

### Option A: Parquet-only (no database required)

```bash
# Terminal 1 -- API
source venv/bin/activate
uvicorn web.api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 -- Frontend
cd web/frontend && npm run dev
```

The API reads from `data/gold/projections/` and `data/gold/predictions/` by default.

### Option B: With PostgreSQL via Docker Compose

```bash
# Start PostgreSQL (schema auto-applied) + API
docker compose up postgres api

# Load data into the database
export DATABASE_URL=postgresql://nfl:nfl_local_2026@localhost:5432/nfl_data
python web/db/load_data.py --season 2024 --week 17

# Terminal 2 -- Frontend
cd web/frontend && npm run dev
```

### Option C: Full Docker Compose stack

```bash
docker compose up          # postgres + api + neo4j
cd web/frontend && npm run dev   # frontend runs separately
```

## Database Setup

### Local (Docker)

Docker Compose auto-applies `web/db/schema.sql` on first start. No manual setup needed.

### Supabase (Production)

1. Create a new Supabase project
2. Run `web/db/schema.sql` in the SQL editor
3. Copy the connection string to `DATABASE_URL`

### Loading Data

```bash
# Load projections and predictions for a specific week
python web/db/load_data.py --season 2024 --week 17

# Load only projections
python web/db/load_data.py --season 2024 --week 17 --type projections

# Load only predictions
python web/db/load_data.py --season 2024 --week 17 --type predictions
```

The loader uses upsert (INSERT ON CONFLICT UPDATE) so it is safe to run repeatedly.

## Deployment

### Frontend (Vercel)

1. Connect the repo to Vercel, set root directory to `web/frontend`
2. Add environment variable: `NEXT_PUBLIC_API_URL` = your API URL
3. Pushes to `main` auto-deploy via `.github/workflows/deploy-web.yml`

### Backend (AWS Lambda)

```bash
cd web/api/serverless
sam build
sam deploy --guided
```

Or via Docker to any container host:

```bash
docker build -f web/Dockerfile -t nfl-data-api .
docker run -p 8000:8000 -e DATABASE_URL=... nfl-data-api
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | No | (none) | PostgreSQL connection string; omit for Parquet fallback |
| `CORS_ORIGINS` | No | `localhost:3000,localhost:8000` | Comma-separated allowed origins |
| `NFL_DATA_DIR` | No | `<project_root>/data` | Base data directory for Parquet reads |
| `NEXT_PUBLIC_API_URL` | Yes (frontend) | `http://localhost:8000` | API base URL for the Next.js client |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check with DB status |
| GET | `/api/projections` | Player projections (season, week, scoring) |
| GET | `/api/projections/top` | Top N projected players |
| GET | `/api/predictions` | Game predictions (season, week) |
| GET | `/api/predictions/{game_id}` | Single game prediction |
| GET | `/api/players/search` | Player name search |
| GET | `/api/players/{player_id}` | Player detail |

Interactive docs at `/api/docs` when running locally.
