# NFL Data Engineering -- Web Platform

## Architecture

```
Next.js (Vercel)  -->  FastAPI (HF Spaces)  -->  Parquet files (data/ in repo clone)
```

- **Frontend**: Next.js app at `web/frontend/`, deployed to Vercel — https://frontend-jet-seven-33.vercel.app
- **Backend**: FastAPI app at `web/api/`, hosted on Hugging Face Spaces — https://gesmith0606-nfl-data-api.hf.space
- **Data**: Parquet files read from a shallow clone of this repo baked into the HF Space image at build time. No live database.
- **Fallback**: `DATABASE_URL` is not set in production; the API reads directly from committed Parquet under `data/`.

> **Railway is no longer in use.** The Railway trial expired in May 2026. All backend traffic goes to HF Spaces.

## Local Development

### Option A: Parquet-only (no database required)

```bash
# Terminal 1 -- API
source venv/bin/activate
./web/run_dev.sh
# Or directly:
uvicorn web.api.main:app --reload --port 8000

# Terminal 2 -- Frontend
cd web/frontend
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
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

Connected via Vercel git integration with **Root Directory** = `web/frontend`. Every push to `main` auto-deploys — no manual step needed.

Set `NEXT_PUBLIC_API_URL` in Vercel project settings (Environment Variables) to the backend URL:
`https://gesmith0606-nfl-data-api.hf.space`

### Backend (HF Spaces)

The HF Space shallow-clones this repo at build time and runs in Parquet-fallback mode. See `deploy/huggingface/README.md` for the data-refresh (CACHE_BUST) pattern and manual rebuild procedure — that file is the source of truth for HF Spaces operations; do not duplicate it here.

Data refresh is triggered automatically by `.github/workflows/deploy-web.yml` (`deploy-backend` job): it bumps `CACHE_BUST` in the Space Dockerfile and calls the HF factory-rebuild API.

**Note (TD-09):** Any `data/` path the Dockerfile COPYs must have a matching `!data/.../**/*.parquet` allowlist in `.gitignore` and be committed to git. An uncommitted path causes builds to silently use a stale image. See CLAUDE.md TD-09 for the full list.

### Deploy gate (SANITY-M6)

`.github/workflows/deploy-web.yml` runs `scripts/sanity_check_projections.py` before any deploy. A CRITICAL exit blocks both the frontend and backend jobs. A present-but-stale or garbage weekly partition also blocks deploy; a missing partition is a SKIP (the API falls back to preseason data). After deploy, a live gate probes the backend and frontend; failure triggers auto-rollback within a 5-minute window.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | No | (none) | PostgreSQL connection string; omit for Parquet fallback |
| `CORS_ORIGINS` | No | `localhost:3000,localhost:8000` | Comma-separated allowed origins |
| `NFL_DATA_DIR` | No | `<project_root>/data` | Base data directory for Parquet reads |
| `API_KEY` | No | (none) | When set, enables X-API-Key auth middleware; health/docs/openapi paths are exempt |
| `NEXT_PUBLIC_API_URL` | Yes (frontend) | `http://localhost:8000` | API base URL for the Next.js client |

## API Endpoints (selected)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/version` | Deployed commit SHA + version info |
| GET | `/api/ops/dashboard` | Ops dashboard |
| GET | `/api/projections?season=&week=&scoring=&position=` | Weekly projections |
| GET | `/api/projections/latest-week` | Most recent week with projection data |
| GET | `/api/projections/top` | Top projections by position |
| GET | `/api/projections/comparison` | Cross-format projection comparison |
| GET | `/api/predictions` | Game predictions with edges (query: season/week) |
| GET | `/api/predictions/{game_id}` | Single game prediction detail |
| GET | `/api/players/search` | Fuzzy player name search |
| GET | `/api/players/{player_id}` | Player detail + history |
| GET | `/api/lineups` | Optimal lineup builder |
| GET | `/api/games` | Game results archive (query filters) |
| GET | `/api/games/{game_id}` | Game detail with player stats |
| GET | `/api/news/feed` | Recent articles and sentiment |
| GET | `/api/news/player-badges/{player_id}` | Player injury + sentiment badges |
| GET | `/api/rankings/external` | External rankings (Sleeper/FantasyPros/ESPN) |
| GET | `/api/rankings/compare` | Our projections vs external source |
| GET | `/api/rankings/multi-compare` | Multi-source ranking comparison |
| GET | `/api/teams/{team}/defense-metrics` | Team positional defense strength |
| GET | `/api/draft/board` | Draft board with VORP + ADP |

Routers: projections, predictions, players, lineups, games, news, draft, rankings, sleeper_user (+ its league router), teams, teams_defense, health_freshness, ops.

Unhandled errors return a generic HTTP 500 with no exception details; diagnose via server logs.

Full OpenAPI docs at `/api/docs` when running locally.
