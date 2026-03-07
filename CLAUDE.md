# CLAUDE.md

## Development Commands

```bash
# Environment (required before all operations)
source venv/bin/activate

# Testing
python -m pytest tests/ -v
python scripts/validate_project.py

# Bronze ingestion
python scripts/bronze_ingestion_simple.py --season 2024 --week 1 --data-type player_weekly
python scripts/bronze_ingestion_simple.py --season 2024 --data-type player_seasonal
# data-types: schedules, pbp, teams, player_weekly, snap_counts, injuries, rosters, player_seasonal

# Silver → Gold → Draft
python scripts/silver_player_transformation.py --seasons 2020 2021 2022 2023 2024
python scripts/generate_projections.py --preseason --season 2026 --scoring half_ppr
python scripts/generate_projections.py --week 1 --season 2026 --scoring ppr
python scripts/draft_assistant.py --scoring half_ppr --teams 12 --my-pick 5

# Backtesting & ADP
python scripts/backtest_projections.py --seasons 2022,2023,2024 --scoring half_ppr
python scripts/refresh_adp.py --season 2026

# Code quality
python -m black src/ tests/ scripts/
python -m flake8 src/ tests/ scripts/
```

### Skills
```
/ingest 2024 1 player_weekly      # Bronze ingestion (Sleeper MCP for ADP/rosters)
/weekly-pipeline 2026 1 half_ppr  # Full Bronze→Silver→Gold chain
/validate-data 2024 10            # Business rules + DuckDB SQL on Parquet
/test                             # Full test suite
/draft-prep 2026 half_ppr 5 12    # Draft workflow (Sleeper + fetch MCPs)
/simplify                         # Code quality review of changed files
```

## Architecture

```
nfl-data-py + Sleeper API
        ↓
Bronze (s3://nfl-raw/)     — raw game, player, snap, injury, roster data
        ↓
Silver (s3://nfl-refined/) — usage metrics, rolling averages, opp rankings (1-32)
        ↓
Gold   (s3://nfl-trusted/) — weekly + preseason projections (PPR/Half-PPR/Standard)
        ↓
Draft Tool                 — ADP comparison, VORP, mock draft, auction, waiver wire
        ↓
[Phase 5 deferred] Neo4j  — WR-CB matchup graphs, target share networks
```

S3 key pattern: `dataset/season=YYYY/week=WW/filename_YYYYMMDD_HHMMSS.parquet`
**Read rule**: always use `download_latest_parquet()` from `src/utils.py` — never scan full prefix.

## Key Files

| File | Purpose |
|------|---------|
| `src/config.py` | S3 paths, SCORING_CONFIGS, ROSTER_CONFIGS, PLAYER_DATA_SEASONS |
| `src/nfl_data_integration.py` | NFLDataFetcher — all 8 fetch methods + validate_data() |
| `src/player_analytics.py` | Usage metrics, opp rankings, rolling avgs, Vegas implied totals |
| `src/scoring_calculator.py` | Fantasy points — single dict + vectorized DataFrame |
| `src/projection_engine.py` | Weekly/preseason projections; bye week, rookie fallback, Vegas multiplier |
| `src/draft_optimizer.py` | DraftBoard, AuctionDraftBoard, MockDraftSimulator, DraftAdvisor |
| `src/utils.py` | Shared utils incl. `get_latest_s3_key`, `download_latest_parquet` |
| `scripts/bronze_ingestion_simple.py` | Bronze CLI — all 8 data types |
| `scripts/silver_player_transformation.py` | Silver CLI |
| `scripts/generate_projections.py` | Gold CLI — `--week` or `--preseason` |
| `scripts/draft_assistant.py` | Interactive draft CLI — snake, auction (`--auction`), simulation (`--simulate`) |
| `scripts/backtest_projections.py` | Compare projected vs actual; MAE/RMSE/bias per position |
| `scripts/refresh_adp.py` | Fetch ADP from Sleeper API → data/adp_latest.csv |
| `scripts/check_pipeline_health.py` | S3 freshness + size checks across all layers |
| `.github/workflows/weekly-pipeline.yml` | Tuesday cron; auto-opens GitHub issue on failure |

## Configuration

- **AWS**: Region us-east-2 | Buckets: `nfl-raw`, `nfl-refined`, `nfl-trusted`
- **Scoring**: PPR (1.0/rec), Half-PPR (0.5/rec), Standard (0.0) — all: 0.1/yd, 6/TD, 0.04/pass yd
- **Roster formats**: `standard`, `superflex`, `2qb` (see `ROSTER_CONFIGS` in config.py)
- **MCPs**: aws-core, aws-s3, aws-docs, github, duckduckgo, duckdb, fetch, sleeper (neo4j configured/disabled)
- **Credentials**: `.env` file (never commit — already in .gitignore; pre-commit hook blocks key patterns)

## NFL Business Rules

- Valid seasons: 1999–2026 | Weeks: 1–18 regular season
- 32 teams | Down: 1–4 | Distance: 1–99 | Yard line: 0–100
- Projected points always ≥ 0 for skill positions (QB/RB/WR/TE)
- Player training data: 2020–2025 (`PLAYER_DATA_SEASONS` in config.py)

## Development Patterns

- **DataFrames** for all processing | **Parquet** for storage | always partition by `season/week`
- Validate at layer boundaries with `NFLDataFetcher.validate_data()`
- Error handling required for: NFL API timeouts, S3 operations, missing columns
- Type hints + Google-style docstrings on all functions
- Follow patterns in `src/nfl_data_integration.py`
- Agent workflow for significant changes: see `.claude/AGENT_FRAMEWORK.md`

## Status

**Done**: Bronze (8 types) → Silver (usage/rolling/rankings) → Gold (projections w/ injury adjustments, regression shrinkage, floor/ceiling) → Draft tool (snake/auction/mock/waiver) → Pipeline monitoring (GHA + health check) → S3 deduplication fix → Projection engine (bye weeks, rookies, Vegas lines) → Backtesting (MAE 4.91, r=0.52 across 3 seasons) → Sleeper ADP refresh → 71 unit tests passing

**In progress**: Weekly pipeline cron tuning | Local-first data reads (S3 as fallback)

**Planned**: Neo4j Phase 5 | ML upgrade (RF/XGBoost) | Live Sleeper league integration
