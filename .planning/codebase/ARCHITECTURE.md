# Architecture

**Analysis Date:** 2026-03-07

## Pattern Overview

**Overall:** Medallion Architecture (Bronze / Silver / Gold) with CLI-driven ETL pipeline

**Key Characteristics:**
- Three-layer data pipeline: raw ingestion (Bronze) → analytics transformations (Silver) → fantasy projections (Gold)
- Functional module design in `src/` — no framework, pure Python with pandas/numpy
- CLI scripts in `scripts/` orchestrate the pipeline stages via `argparse`
- Local-first data storage with optional S3 upload; each layer writes timestamped Parquet files
- No web server or API layer — all output is Parquet files or interactive CLI sessions

## Layers

**Bronze (Raw Ingestion):**
- Purpose: Fetch raw NFL data from `nfl-data-py` library and persist as Parquet
- Location: `data/bronze/` (local), `s3://nfl-raw/` (remote)
- Contains: 8 data types — schedules, pbp, teams, player_weekly, snap_counts, injuries, rosters, player_seasonal
- Depends on: `nfl-data-py` Python package, AWS S3 (optional)
- Used by: Silver layer scripts
- Entry point: `scripts/bronze_ingestion_simple.py`
- Key class: `src/nfl_data_integration.py` → `NFLDataFetcher` (8 fetch methods + `validate_data()`)

**Silver (Analytics Transformations):**
- Purpose: Compute derived metrics from Bronze data — usage shares, rolling averages, opponent rankings, game script indicators, venue splits
- Location: `data/silver/` (local), `s3://nfl-refined/` (remote)
- Contains: Usage metrics per player-week, opponent defensive rankings (1-32), rolling averages (3-week, 6-week, season-to-date)
- Depends on: Bronze layer Parquet files, `src/player_analytics.py`
- Used by: Gold layer projection engine
- Entry point: `scripts/silver_player_transformation.py`

**Gold (Projections):**
- Purpose: Generate fantasy football point projections using weighted averages, matchup adjustments, and scoring format conversion
- Location: `data/gold/` (local), `s3://nfl-trusted/` (remote)
- Contains: Weekly and preseason projections with floor/ceiling ranges
- Depends on: Silver layer data, `src/projection_engine.py`, `src/scoring_calculator.py`
- Used by: Draft assistant tool, backtesting script
- Entry point: `scripts/generate_projections.py`

**Draft/Consumer Layer:**
- Purpose: Interactive draft assistance using Gold projections + ADP data
- Location: No persistent storage (interactive CLI session)
- Contains: Draft board management, VORP calculations, mock draft simulation, auction support, waiver wire
- Depends on: Gold projections, ADP data (`data/adp_latest.csv`)
- Entry point: `scripts/draft_assistant.py`

## Data Flow

**Weekly Pipeline (Bronze → Silver → Gold):**

1. `scripts/bronze_ingestion_simple.py` fetches data from `nfl-data-py` for a specific season/week
2. Data is saved as timestamped Parquet files to `data/bronze/players/{type}/season={YYYY}/`
3. `scripts/silver_player_transformation.py` reads Bronze Parquet, runs analytics from `src/player_analytics.py`
4. Silver output (usage metrics, rolling averages, opponent rankings) written to `data/silver/`
5. `scripts/generate_projections.py` reads Silver data, runs `src/projection_engine.py`
6. Gold projections (with injury adjustments, floor/ceiling) written to `data/gold/projections/`

**Projection Model Pipeline:**

1. Load rolling averages from Silver layer (3-week, 6-week, season-to-date)
2. Blend via `RECENCY_WEIGHTS`: roll3 (0.45) + roll6 (0.30) + std (0.25)
3. Apply usage multiplier [0.80-1.15] based on snap%/target share
4. Apply matchup factor [0.85-1.15] from opponent defensive rankings
5. Apply Vegas multiplier from implied team totals (total_line / 23.0)
6. Convert projected stats → fantasy points via `src/scoring_calculator.py`
7. Apply ceiling shrinkage at 15/20/25 pt thresholds
8. Apply injury adjustments (status multipliers: Active=1.0, Questionable=0.85, etc.)
9. Add floor/ceiling ranges (position-specific variance: QB 45%, RB 40%, WR 38%, TE 35%)

**Draft Preparation Flow:**

1. Generate preseason projections (Gold layer)
2. Load ADP data from `data/adp_latest.csv` (fetched via `scripts/refresh_adp.py` from Sleeper API)
3. Compute value scores: model_rank, adp_diff, VORP
4. Initialize `DraftBoard` or `AuctionDraftBoard`
5. Interactive CLI loop: draft/pick/recommend/waiver commands

**State Management:**
- No runtime state between pipeline stages — each script reads Parquet files independently
- S3 uses timestamped keys for versioning; readers use `download_latest_parquet()` to resolve latest
- Local files use sorted glob to pick the latest timestamped file
- Draft assistant maintains in-memory `DraftBoard` state during interactive session

## Key Abstractions

**NFLDataFetcher:**
- Purpose: Unified interface to `nfl-data-py` library with validation
- Location: `src/nfl_data_integration.py`
- Pattern: Single class with 8 `fetch_*` methods + `validate_data()` method
- All methods return `pd.DataFrame` with `data_source` and `ingestion_timestamp` metadata columns

**Player Analytics Functions:**
- Purpose: Compute derived Silver-layer metrics
- Location: `src/player_analytics.py`
- Pattern: Stateless functions that take DataFrames and return enriched DataFrames
- Functions: `compute_usage_metrics()`, `compute_opponent_rankings()`, `compute_rolling_averages()`, `compute_game_script_indicators()`, `compute_venue_splits()`, `compute_implied_team_totals()`

**Projection Engine:**
- Purpose: Generate fantasy point projections from Silver data
- Location: `src/projection_engine.py`
- Pattern: Module-level constants for weights/baselines + pure functions
- Key functions: `generate_weekly_projections()`, `generate_preseason_projections()`, `apply_injury_adjustments()`, `add_floor_ceiling()`
- Internal helpers: `_weighted_baseline()`, `_usage_multiplier()`, `_matchup_factor()`, `_vegas_multiplier()`, `_rookie_baseline()`

**Scoring Calculator:**
- Purpose: Convert stat lines to fantasy points
- Location: `src/scoring_calculator.py`
- Pattern: Two modes — single-dict (`calculate_fantasy_points()`) and vectorized DataFrame (`calculate_fantasy_points_df()`)
- Config-driven via `SCORING_CONFIGS` from `src/config.py`

**Draft Optimizer Classes:**
- Purpose: Draft board management and recommendations
- Location: `src/draft_optimizer.py`
- Classes: `DraftBoard` (base), `AuctionDraftBoard(DraftBoard)`, `MockDraftSimulator`, `DraftAdvisor`
- Pattern: Stateful objects managing draft state with method-based API

**S3 Read Convention:**
- Purpose: Prevent duplicate rows from accumulating timestamped files
- Location: `src/utils.py`
- Functions: `get_latest_s3_key()`, `download_latest_parquet()`
- Rule: ALWAYS use `download_latest_parquet()` — never scan full S3 prefix

## Entry Points

**Bronze Ingestion CLI:**
- Location: `scripts/bronze_ingestion_simple.py`
- Triggers: Manual CLI, GitHub Actions cron (Tuesday 09:00 UTC)
- Arguments: `--season`, `--week`, `--data-type` (one of 8 types)
- Responsibilities: Fetch from nfl-data-py, validate, write Parquet to local + optional S3

**Silver Transformation CLI:**
- Location: `scripts/silver_player_transformation.py`
- Triggers: Manual CLI, GitHub Actions pipeline
- Arguments: `--season`/`--seasons`, `--week` (optional)
- Responsibilities: Read Bronze, compute usage/rolling/rankings, write Silver Parquet

**Gold Projection CLI:**
- Location: `scripts/generate_projections.py`
- Triggers: Manual CLI, GitHub Actions pipeline
- Arguments: `--season`, `--week` or `--preseason`, `--scoring`
- Responsibilities: Read Silver, generate projections, apply adjustments, write Gold Parquet

**Draft Assistant CLI:**
- Location: `scripts/draft_assistant.py`
- Triggers: Manual CLI only
- Arguments: `--scoring`, `--teams`, `--my-pick`, `--auction`, `--simulate`
- Responsibilities: Interactive draft session with recommendations, VORP, ADP comparison

**Backtesting CLI:**
- Location: `scripts/backtest_projections.py`
- Triggers: Manual CLI only
- Arguments: `--seasons`, `--scoring`
- Responsibilities: Compare projections vs actuals; compute MAE/RMSE/bias per position

**Health Check CLI:**
- Location: `scripts/check_pipeline_health.py`
- Triggers: Manual CLI, GitHub Actions pipeline
- Arguments: `--season`, `--week`, `--layer`
- Responsibilities: Validate S3 file freshness and sizes across all layers

**GitHub Actions Workflow:**
- Location: `.github/workflows/weekly-pipeline.yml`
- Triggers: Cron (Tuesday 09:00 UTC), manual `workflow_dispatch`
- Jobs: `compute-week` → `run-pipeline` (Bronze→Silver→Gold→Health) → `notify-failure` (opens GitHub issue)

## Error Handling

**Strategy:** Try/except with logging at module boundaries; raise to caller

**Patterns:**
- All `NFLDataFetcher.fetch_*()` methods wrap in try/except, log errors, then re-raise
- S3 operations use `botocore.exceptions.ClientError` for specific AWS error handling
- `download_latest_parquet()` returns empty DataFrame on failure (does not raise)
- Scripts use `continue-on-error: true` in GitHub Actions for non-critical steps (e.g., roster ingestion)
- Season validation: reject seasons outside 1999-2026 range with `ValueError`

## Cross-Cutting Concerns

**Logging:** Python `logging` module; each module creates `logger = logging.getLogger(__name__)`; configured at `INFO` level via `logging.basicConfig(level=logging.INFO)` in `src/utils.py` and `src/nfl_data_integration.py`

**Validation:** `NFLDataFetcher.validate_data()` checks required columns, null percentages, and data-type-specific rules (duplicate game_ids, season ranges). Called at Bronze ingestion boundary.

**Configuration:** Centralized in `src/config.py` — S3 paths, scoring configs, roster configs, S3 key templates. Environment variables loaded from `.env` via `python-dotenv`.

**Data Partitioning:** All layers use Hive-style partitioning: `dataset/season=YYYY/week=WW/filename_YYYYMMDD_HHMMSS.parquet`. Season-level data omits the week partition.

---

*Architecture analysis: 2026-03-07*
