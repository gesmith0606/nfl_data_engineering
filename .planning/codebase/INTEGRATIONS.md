# External Integrations

**Analysis Date:** 2026-03-07

## APIs & External Services

**NFL Data (Primary Data Source):**
- nfl_data_py (nflverse) - All historical NFL statistics: schedules, play-by-play, weekly player stats, snap counts, injuries, rosters, seasonal aggregates
  - SDK/Client: `nfl_data_py` package (v0.3.3)
  - Auth: None (public GitHub-hosted data)
  - Integration: `src/nfl_data_integration.py` - `NFLDataFetcher` class with 8 fetch methods
  - Data types: `schedules`, `pbp`, `teams`, `player_weekly`, `snap_counts`, `injuries`, `rosters`, `player_seasonal`
  - Coverage: Seasons 1999-2026

**Sleeper API (Fantasy Platform):**
- ADP data and player database for draft optimization
  - Base URL: `https://api.sleeper.app/v1/`
  - Endpoints used:
    - `GET /players/nfl` - Full player database (search_rank, position, team, years_exp)
    - `GET /projections/nfl/regular/{season}/{week}` - Weekly fantasy projections
  - Auth: None (public API)
  - Integration: `scripts/refresh_adp.py` - `fetch_sleeper_players()`, `fetch_sleeper_projections()`
  - Output: `data/adp_latest.csv`
  - Timeout: 60 seconds per request

## Data Storage

**Databases:**
- AWS S3 (object storage as data lake)
  - Region: us-east-2
  - Buckets:
    - `nfl-raw` (Bronze layer) - Raw ingested data
    - `nfl-refined` (Silver layer) - Transformed analytics
    - `nfl-trusted` (Gold layer) - Final projections
  - Connection: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` env vars
  - Client: `boto3` S3 client (direct, no ORM)
  - Key pattern: `dataset/season=YYYY/week=WW/filename_YYYYMMDD_HHMMSS.parquet`
  - Read convention: Always use `download_latest_parquet()` from `src/utils.py` - never scan full prefix

**Local File Storage:**
- Local mirrors of S3 data in `data/bronze/`, `data/silver/`, `data/gold/`
- Same partition structure as S3 (`season=YYYY/week=WW/`)
- Primary read path when AWS credentials are expired (current state)
- Scripts support local reads with S3 fallback: `scripts/silver_player_transformation.py`, `scripts/generate_projections.py`, `scripts/backtest_projections.py`

**File Storage:**
- Parquet format exclusively for all data files
- CSV for ADP data: `data/adp_latest.csv`

**Caching:**
- None (no Redis/Memcached)

## Authentication & Identity

**Auth Provider:**
- None - this is a data pipeline, not a user-facing application
- AWS IAM credentials used for S3 access only

## Monitoring & Observability

**Error Tracking:**
- GitHub Issues (auto-created on pipeline failure via `.github/workflows/weekly-pipeline.yml`)
- Labels: `pipeline-failure`, `automated`

**Logs:**
- Python `logging` module throughout all src/ and scripts/
- `logging.basicConfig(level=logging.INFO)` in each module
- Per-module loggers via `logging.getLogger(__name__)`
- No structured logging in practice (structlog installed but not used)

**Health Checks:**
- `scripts/check_pipeline_health.py` - S3 freshness and file size validation across all layers
- Configurable max age via `HEALTH_CHECK_MAX_AGE_DAYS` env var (default: 8 days)

## CI/CD & Deployment

**Hosting:**
- AWS S3 for data storage (no application hosting)
- GitHub for source code

**CI Pipeline:**
- GitHub Actions: `.github/workflows/weekly-pipeline.yml`
  - Schedule: Tuesdays 09:00 UTC (after Monday Night Football)
  - Manual trigger: `gh workflow run weekly-pipeline.yml -f season=2024 -f week=10`
  - Concurrency: single pipeline group, no cancel-in-progress
  - Jobs:
    1. `compute-week` - Auto-detect NFL season/week from date
    2. `run-pipeline` - Bronze (4 data types) -> Silver -> Gold (half_ppr) -> Health check
    3. `notify-failure` - Open GitHub issue on failure
  - Runner: ubuntu-latest, Python 3.11
  - AWS credentials: `aws-actions/configure-aws-credentials@v4`

## Environment Configuration

**Required env vars (for S3 operations):**
- `AWS_ACCESS_KEY_ID` - AWS IAM access key
- `AWS_SECRET_ACCESS_KEY` - AWS IAM secret key
- `AWS_REGION` - Defaults to `us-east-2`

**Optional env vars:**
- `S3_BUCKET_BRONZE` - Defaults to `nfl-raw`
- `S3_BUCKET_SILVER` - Defaults to `nfl-refined`
- `S3_BUCKET_GOLD` - Defaults to `nfl-trusted`
- `DATABRICKS_WORKSPACE_URL` - Configured but not actively used
- `DATABRICKS_CLUSTER_ID` - Configured but not actively used
- `DATABRICKS_TOKEN` - Configured but not actively used
- `PIPELINE_WEEK_OVERRIDE` - Format `YYYY:WW`, overrides auto-computed week
- `HEALTH_CHECK_MAX_AGE_DAYS` - Freshness threshold (default: 8)
- `LOG_LEVEL` - Logging verbosity (default: INFO)

**Secrets location:**
- Local: `.env` file (in `.gitignore`, never committed)
- CI: GitHub Actions Secrets (Settings -> Secrets and variables -> Actions)
- Pre-commit hook blocks credential patterns from being staged

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- GitHub Issues API (via `actions/github-script@v7` in CI) - auto-opens issues on pipeline failure using built-in `GITHUB_TOKEN`

## MCP Servers (Claude Code Integration)

**Enabled:**
- `aws-core`, `aws-s3`, `aws-docs` - AWS operations
- `github-server` - PR/issue/branch management
- `duckduckgo-search` - Web search
- `duckdb` - SQL on Parquet files (used in `/validate-data`)
- `fetch` - HTTP requests (FantasyPros ADP scraping)
- `sleeper` - Sleeper API for ADP, rosters, leagues

**Configured but Disabled:**
- `neo4j` - Phase 5 (WR-CB matchup graphs, target share networks) - deferred

## Dormant / Planned Integrations

**Databricks:**
- Workspace URL and cluster configured in `src/config.py` and `.env.example`
- Not actively used - PySpark import is guarded in `src/utils.py`
- Delta Lake extensions configured in Spark session builder

**Neo4j:**
- Phase 5 planned feature for WR-CB matchup graphs and QB-WR networks
- MCP server configured but disabled

---

*Integration audit: 2026-03-07*
