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
# data-types: schedules, pbp, teams, player_weekly, snap_counts, injuries, rosters, player_seasonal, ngs, pfr_stats, qbr, depth_charts, draft_picks, combine, officials

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
Bronze (s3://nfl-raw/)     — 15+ data types: PBP (140 cols), player stats, schedules,
                              snap counts, injuries, rosters, NGS, PFR, QBR, depth charts,
                              draft picks, combine, officials, teams
        ↓
Silver (s3://nfl-refined/) — 12 paths: player usage/advanced/historical, team PBP metrics/
                              tendencies/SOS/situational, game context, referee, defense,
                              playoff context, PBP-derived (164 cols)
        ↓
Gold   (s3://nfl-trusted/) — fantasy projections (PPR/Half-PPR/Standard) + game predictions (v1.4)
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
| `src/nfl_data_adapter.py` | NFLDataAdapter — unified data fetching with local-first reads |
| `src/nfl_data_integration.py` | NFLDataFetcher — legacy fetcher (see nfl_data_adapter.py) + validate_data() |
| `src/player_analytics.py` | Usage metrics, opp rankings, rolling avgs, Vegas implied totals |
| `src/team_analytics.py` | Team PBP metrics, tendencies, SOS, situational splits |
| `src/player_advanced_analytics.py` | Advanced player profiles, target shares, efficiency metrics |
| `src/game_context.py` | Game context features, referee tendencies, playoff context, defense positional |
| `src/historical_profiles.py` | Career trajectories, historical performance, rookie/veteran classification |
| `src/scoring_calculator.py` | Fantasy points — single dict + vectorized DataFrame |
| `src/projection_engine.py` | Weekly/preseason projections; bye week, rookie fallback, Vegas multiplier |
| `src/draft_optimizer.py` | DraftBoard, AuctionDraftBoard, MockDraftSimulator, DraftAdvisor |
| `src/utils.py` | Shared utils incl. `get_latest_s3_key`, `download_latest_parquet` |
| `scripts/bronze_ingestion_simple.py` | Bronze CLI — all 15+ data types via registry |
| `scripts/silver_player_transformation.py` | Silver player CLI — usage metrics, rolling averages |
| `scripts/silver_team_transformation.py` | Silver team CLI — PBP metrics, tendencies, SOS, situational |
| `scripts/silver_game_context_transformation.py` | Silver game context CLI — weather, referee, playoff, defense |
| `scripts/silver_advanced_transformation.py` | Silver advanced profiles CLI — NGS/PFR/QBR merge |
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

**Done**: v1.0 Bronze Expansion (15+ data types, PBP 140 cols) → v1.1 Bronze Backfill (2020-2025 historical) → v1.2 Silver Expansion (12 Silver paths, team/player/game analytics) → v1.3 Prediction Data Foundation (337-col feature vector, cross-source validation) → Fantasy: projections (PPR/Half/Standard, bye/rookie/Vegas/injury), draft tool (snake/auction/mock/waiver), backtesting (MAE 4.91) → 360 tests passing

**In progress**: v1.4 ML Game Prediction (XGBoost spread/total models, walk-forward CV, edge detection)

**Planned**: Neo4j Phase 5 (WR-CB matchups, target networks) | Live Sleeper league integration

## ECC Plugin (Everything Claude Code)

Installed via `/plugin install everything-claude-code@everything-claude-code`.
Rules (common + Python) installed in `.claude/rules/`. Full repo at `~/repos/everything-claude-code/` — `git pull` to update.

**Key ECC commands**: `/plan`, `/tdd`, `/code-review`, `/build-fix`, `/e2e`, `/security-scan`, `/verify`, `/learn`, `/compact`
**ECC rules active in `.claude/rules/`**: coding-style, git-workflow, testing, performance, patterns, hooks, agents, security, development-workflow (Python)

## GSD (Get Shit Done) v1.22.4

Installed locally via `npx get-shit-done-cc@latest --claude --local`. Full repo at `~/repos/get-shit-done/` — `git pull` to update.

**Core workflow**: `/gsd:new-project` → `/gsd:discuss-phase N` → `/gsd:plan-phase N` → `/gsd:execute-phase N` → `/gsd:verify-work N`
**Quick tasks**: `/gsd:quick` — ad-hoc tasks with GSD guarantees (atomic commits, state tracking)
**Brownfield**: `/gsd:map-codebase` — analyze existing code before planning new work
**Utilities**: `/gsd:progress`, `/gsd:pause-work`, `/gsd:resume-work`, `/gsd:debug`
**Update**: `npx get-shit-done-cc@latest`

## Reference Repos

These repos are cloned locally for reference, updates, and reuse across projects:
- `~/repos/everything-claude-code/` — ECC guides, skills, rules, examples. See `the-shortform-guide.md` and `the-longform-guide.md` for advanced patterns.
- `~/repos/get-shit-done/` — GSD source, docs, and user guide at `docs/USER-GUIDE.md`.
