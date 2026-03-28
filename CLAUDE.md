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
python scripts/bronze_odds_ingestion.py --season 2020
# data-types: schedules, pbp, teams, player_weekly, snap_counts, injuries, rosters, player_seasonal, ngs, pfr_stats, qbr, depth_charts, draft_picks, combine, officials, odds

# Silver transformations
python scripts/silver_player_transformation.py --seasons 2020 2021 2022 2023 2024
python scripts/silver_team_transformation.py --seasons 2020 2021 2022 2023 2024
python scripts/silver_market_transformation.py --season 2020
python scripts/silver_player_quality_transformation.py --seasons 2020 2021 2022 2023 2024

# Gold: Fantasy projections
python scripts/generate_projections.py --preseason --season 2026 --scoring half_ppr
python scripts/generate_projections.py --week 1 --season 2026 --scoring ppr
python scripts/draft_assistant.py --scoring half_ppr --teams 12 --my-pick 5

# Gold: Game predictions
python scripts/train_ensemble.py                    # Train XGB+LGB+CB+Ridge ensemble
python scripts/train_ensemble.py --tune             # With Optuna hyperparameter tuning
python scripts/run_feature_selection.py             # CV-validated SHAP feature selection
python scripts/generate_predictions.py --ensemble   # Weekly predictions with edge detection
python scripts/backtest_predictions.py --ensemble   # ATS/O-U/CLV evaluation
python scripts/backtest_predictions.py --holdout    # Sealed 2024 holdout comparison
python scripts/ablation_market_features.py          # Market feature ablation on holdout

# Fantasy backtesting & ADP
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
nfl-data-py + Sleeper API + FinnedAI odds
        ↓
Bronze (s3://nfl-raw/)     — 16 data types: PBP (140 cols), player stats, schedules,
                              snap counts, injuries, rosters, NGS, PFR, QBR, depth charts,
                              draft picks, combine, officials, teams, odds (2016-2021)
        ↓
Silver (s3://nfl-refined/) — 14 paths: player usage/advanced/historical/quality, team PBP
                              metrics/tendencies/SOS/situational/PBP-derived, game
                              context, referee, playoff context, market data (line movement)
        ↓
Gold   (s3://nfl-trusted/) — fantasy projections (PPR/Half-PPR/Standard) + game predictions
                              (v2.0 XGB+LGB+CB+Ridge ensemble, CLV tracking)
        ↓
Draft Tool                 — ADP comparison, VORP, mock draft, auction, waiver wire
        ↓
[Deferred] Neo4j           — WR-CB matchup graphs, target share networks
```

S3 key pattern: `dataset/season=YYYY/week=WW/filename_YYYYMMDD_HHMMSS.parquet`
**Read rule**: always use `download_latest_parquet()` from `src/utils.py` — never scan full prefix.

## Key Files

| File | Purpose |
|------|---------|
| `src/config.py` | S3 paths, SCORING_CONFIGS, ROSTER_CONFIGS, PLAYER_DATA_SEASONS, SILVER paths |
| `src/nfl_data_adapter.py` | NFLDataAdapter — unified data fetching with local-first reads |
| `src/nfl_data_integration.py` | NFLDataFetcher — legacy fetcher (see nfl_data_adapter.py) + validate_data() |
| `src/player_analytics.py` | Usage metrics, opp rankings, rolling avgs, Vegas implied totals |
| `src/team_analytics.py` | Team PBP metrics, tendencies, SOS, situational splits (1834 lines) |
| `src/player_advanced_analytics.py` | Advanced player profiles, target shares, efficiency metrics |
| `src/game_context.py` | Game context features, referee tendencies, playoff context, defense |
| `src/historical_profiles.py` | Career trajectories, combine measurables, draft capital |
| `src/market_analytics.py` | Line movement features, magnitude buckets, per-team reshape |
| `src/feature_engineering.py` | 310+ col feature vector assembly from 10 Silver sources |
| `src/feature_selector.py` | SHAP importance + correlation filtering, CV-validated cutoff |
| `src/ensemble_training.py` | XGB+LGB+CB+Ridge stacking, walk-forward CV, OOF predictions |
| `src/model_training.py` | Walk-forward CV framework, single-model training (legacy) |
| `src/prediction_backtester.py` | ATS/O-U/CLV evaluation, holdout validation, profit analysis |
| `src/scoring_calculator.py` | Fantasy points — single dict + vectorized DataFrame |
| `src/projection_engine.py` | Weekly/preseason projections; bye week, rookie fallback, Vegas multiplier |
| `src/draft_optimizer.py` | DraftBoard, AuctionDraftBoard, MockDraftSimulator, DraftAdvisor |
| `src/utils.py` | Shared utils incl. `get_latest_s3_key`, `download_latest_parquet` |
| `scripts/bronze_ingestion_simple.py` | Bronze CLI — all 16 data types via registry |
| `scripts/bronze_odds_ingestion.py` | Bronze odds CLI — FinnedAI JSON → Parquet (2016-2021) |
| `scripts/silver_player_transformation.py` | Silver player CLI — usage metrics, rolling averages |
| `scripts/silver_team_transformation.py` | Silver team CLI — PBP metrics, tendencies, SOS, situational |
| `scripts/silver_game_context_transformation.py` | Silver game context CLI — weather, referee, playoff, defense |
| `scripts/silver_advanced_transformation.py` | Silver advanced profiles CLI — NGS/PFR/QBR merge |
| `scripts/silver_market_transformation.py` | Silver market CLI — line movement features from Bronze odds |
| `scripts/silver_player_quality_transformation.py` | Silver player quality CLI — QB EPA, injury impact |
| `scripts/train_ensemble.py` | Ensemble training CLI — XGB+LGB+CB+Ridge with optional Optuna |
| `scripts/run_feature_selection.py` | Feature selection CLI — SHAP + correlation, CV-validated |
| `scripts/generate_predictions.py` | Prediction CLI — weekly lines with edge detection vs Vegas |
| `scripts/backtest_predictions.py` | Prediction backtest CLI — ATS/O-U/CLV, holdout comparison |
| `scripts/ablation_market_features.py` | Ablation CLI — P30 baseline vs market features on holdout |
| `scripts/generate_projections.py` | Gold CLI — `--week` or `--preseason` |
| `scripts/draft_assistant.py` | Interactive draft CLI — snake, auction, simulation, waiver wire |
| `scripts/backtest_projections.py` | Fantasy backtest — MAE/RMSE/bias per position |
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

**Done**: v1.0 Bronze Expansion (16 data types, PBP 140 cols) → v1.1 Bronze Backfill (2016-2025 historical, 517 files, 93 MB) → v1.2 Silver Expansion (team/player/game analytics) → v1.3 Prediction Data Foundation (337-col feature vector) → v1.4 ML Game Prediction (XGBoost, walk-forward CV, edge detection) → v2.0 Prediction Model Improvement (XGB+LGB+CB+Ridge ensemble, 53.0% ATS, +$3.09 on sealed 2024 holdout) → v2.1 Market Data (Bronze odds, Silver line movement, CLV tracking, ablation framework) → Fantasy: projections (PPR/Half/Standard), draft tool (snake/auction/mock/waiver), backtesting (MAE 4.91) → 571 tests passing

**In progress**: Planning next milestone

**Planned**: v2.2 Betting Framework (Kelly criterion, EV, line shopping) | v3.0 Production Infra (automated pipeline, drift detection) | Neo4j (WR-CB matchups) | Live Sleeper integration

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
