# NFL Data Engineering Platform

## What This Is

A comprehensive NFL data engineering platform built on Medallion Architecture (Bronze/Silver/Gold) that powers both fantasy football projections and ML game outcome predictions. Features 15 Bronze data types with 10 years of history (2016-2025), a rich Silver layer with 11 output paths, a 337-column prediction feature vector, XGBoost models for point spread and over/under prediction with walk-forward cross-validation, backtesting against historical Vegas closing lines, and a weekly prediction pipeline with edge detection and confidence tiers — plus registry-driven ingestion, batch orchestration, and local-first storage.

## Core Value

A rich, well-modeled NFL data lake that serves as the foundation for both fantasy football decision-making and game prediction models.

## Requirements

### Validated

- ✓ Infrastructure: local-first storage, dynamic season validation, adapter pattern, registry CLI — v1.0
- ✓ PBP: 103 curated columns (EPA/WPA/CPOE/air yards) for 2016-2025, memory-safe batching — v1.0
- ✓ Advanced stats: NGS, PFR weekly/seasonal, QBR, depth charts, draft picks, combine — v1.0
- ✓ Documentation: data dictionary, Bronze inventory, prediction model badges, implementation guide — v1.0
- ✓ Validation: validate_data() for all data types, wired into ingestion pipeline — v1.0
- ✓ Bronze layer: 6 original types (schedules, player_weekly, player_seasonal, snap_counts, injuries, rosters) — pre-v1.0
- ✓ Silver layer: usage metrics, rolling averages, opponent rankings — pre-v1.0
- ✓ Gold layer: weekly + preseason projections (PPR/Half-PPR/Standard) — pre-v1.0
- ✓ Draft tool: snake, auction, mock draft, waiver wire — pre-v1.0
- ✓ Pipeline monitoring: GHA cron + health check — pre-v1.0
- ✓ Backtesting: MAE 4.91, r=0.51 across 3 seasons — pre-v1.0
- ✓ 186 total tests passing — v1.1
- ✓ 9 new Bronze data types ingested with full historical coverage — v1.1
- ✓ 6 existing types backfilled to 2016-2025 (517 files, 93 MB) — v1.1
- ✓ Batch ingestion CLI with progress, failure handling, skip-existing — v1.1
- ✓ 2025 player stats via stats_player adapter with column mapping — v1.1
- ✓ Bronze-Silver path alignment (snap_counts, schedules) — v1.1
- ✓ Bronze inventory: 15 data types, 10 years, all validated — v1.1
- ✓ PBP-derived team metrics (EPA, success rate, CPOE, red zone) with 3/6-game rolling windows — v1.2
- ✓ Team tendencies (pace, PROE, 4th-down aggressiveness, early-down run rate) with rolling windows — v1.2
- ✓ Opponent-adjusted EPA with lagged SOS and schedule difficulty rankings (1-32) — v1.2
- ✓ Situational splits (home/away, divisional, game script) with rolling EPA — v1.2
- ✓ Advanced player profiles (NGS separation/RYOE/TTT, PFR pressure/blitz, QBR) with rolling windows — v1.2
- ✓ Historical dimension table: combine measurables + draft capital for 9,892 players — v1.2
- ✓ Pipeline health monitoring for all 7 Silver paths — v1.2
- ✓ 289 total tests passing — v1.2
- ✓ PBP expanded to 140 columns (penalty, ST, fumble recovery, drive details) with re-ingestion for 2016-2025 — v1.3
- ✓ Officials Bronze ingested for 2016-2025 with referee crew assignments — v1.3
- ✓ Stadium coordinates (38 venues) for haversine travel distance — v1.3
- ✓ 11 PBP-derived team metrics (penalties, turnovers, red zone trips, FG accuracy, returns, 3rd down, explosives, drives, sacks, TOP) with rolling windows — v1.3
- ✓ Game context Silver layer (weather, rest, travel, coaching, surface) per team per week — v1.3
- ✓ Referee tendency profiles (expanding-window penalty rates per crew with shift(1) lag) — v1.3
- ✓ Playoff/elimination context (cumulative W-L-T, division rank, games behind, late-season contention) — v1.3
- ✓ Full prediction feature vector assembly: 337 columns from 8 Silver sources — v1.3
- ✓ Pipeline health monitoring for all 11 Silver paths — v1.3
- ✓ 360 total tests passing — v1.3
- ✓ Game-level differential feature assembly (337-col vectors, home-away differentials) — v1.4
- ✓ XGBoost model training with walk-forward CV (temporal split, holdout guard) — v1.4
- ✓ Training CLI with Optuna hyperparameter tuning and feature importance reporting — v1.4
- ✓ 396 total tests passing — v1.4
- ✓ Prediction backtester with ATS/O-U evaluation and vig-adjusted profit at -110 odds — v1.4
- ✓ Sealed 2024 holdout validation with leakage guard and per-season stability analysis — v1.4
- ✓ 426 total tests passing — v1.4
- ✓ Comprehensive docs refresh (data dictionary for all layers, CLAUDE.md, implementation guide) — v1.4
- ✓ ML prediction model (XGBoost) for point spreads using 337-column feature vector — v1.4
- ✓ ML prediction model (XGBoost) for over/unders using 337-column feature vector — v1.4
- ✓ Backtest ML models against historical closing lines with ATS accuracy and profit analysis — v1.4
- ✓ Weekly prediction pipeline generating own lines with edge detection vs Vegas — v1.4
- ✓ 439 total tests passing — v1.4
- ✓ Player quality Silver features (QB EPA, positional quality, injury impact) — Phase 28, v2.0
- ✓ Feature selection pipeline: SHAP importance + correlation filtering (r > 0.90) with CV-validated cutoff — Phase 29, v2.0
- ✓ Walk-forward-safe feature selection (per-fold, 2024 holdout excluded) — Phase 29, v2.0
- ✓ 470 total tests passing — v2.0
- ✓ Model ensemble: XGBoost + LightGBM + CatBoost stacking with Ridge meta-learner and generalized walk-forward CV — Phase 30, v2.0
- ✓ Ensemble training CLI with optional Optuna tuning, --ensemble flag in backtest and prediction CLIs — Phase 30, v2.0
- ✓ 482 total tests passing — v2.0

### Active

**Current Milestone: v2.0 Prediction Model Improvement**

**Goal:** Transform the baseline prediction model (53% ATS, 50% holdout) into a competitive edge-finding system through player-level features, model ensembles, feature selection, and advanced signal extraction.

**Target features:**
- Player-level features: QB quality metrics (EPA/QBR rolling), starter vs backup detection, key injury impact on team performance
- ~~Model ensemble: XGBoost + LightGBM + CatBoost stacking with Ridge meta-learner~~ (Phase 30 complete)
- ~~Feature selection: Reduce 283 features to optimal subset via importance/correlation filtering~~ (Phase 29 complete)
- Advanced features: Adaptive rolling windows, momentum/trend detection, regime detection
- Leakage fix: Commit the same-week raw stat exclusion from feature engineering (already implemented)

### Planned (Future Milestones)

Full details: `.planning/VISION.md` | Requirements: `.planning/REQUIREMENTS.md`

- v2.0 Player-Level Features — QB quality, injury replacement quality, WR-CB matchups (Neo4j), depth chart deltas, personnel groupings
- v2.1 Model Ensemble — XGBoost + LightGBM + CatBoost + Ridge stacking, probabilistic output, quantile regression
- v2.2 Advanced Features — adaptive rolling windows, momentum/trend, motivation, pace-adjustment, regime detection
- v2.3 Market Data — historical odds database, line movement features, CLV tracking
- v2.4 Betting Framework — Kelly criterion, EV calculation, line shopping, shadow betting tracker, calibration
- v3.0 Production Infra — automated weekly pipeline, in-season retraining, drift detection, A/B testing
- v3.1 Alternative Data — practice reports, coaching decisions, tracking data, news NLP
- Fantasy ML Upgrade — replace weighted-average projections with ML models
- Live Sleeper Integration — real-time league sync and waiver recommendations

### Out of Scope

- S3 sync — AWS credentials expired, local-first workflow active
- nflreadpy migration — requires Python 3.10+; separate future milestone
- Neural networks / deep learning — gradient boosting dominates tabular sports prediction at this data scale
- Real-time prediction serving — batch weekly predictions sufficient

## Context

Shipped v1.4 with 23,571 LOC Python across 27 phases and 50 plans (five milestones).
Tech stack: Python 3.9, pandas, pyarrow, pytz, xgboost, optuna, nfl-data-py, local Parquet storage (S3 optional).
Bronze layer: 15 data types covering schedules, player stats, PBP (140 cols), NGS, PFR, QBR, depth charts, combine, draft picks, teams, injuries, rosters, snap counts, officials — 517 files, 93 MB.
Silver layer: team metrics (EPA, tendencies, SOS, situational, PBP-derived 11 metrics, game context, referee tendencies, playoff context), player metrics (usage, rolling avgs, opp rankings, advanced profiles), historical dimension table — 11 output paths.
Gold layer: weekly + preseason fantasy projections with injury adjustments, regression shrinkage, floor/ceiling; ML game predictions with spread/total models, edge detection, confidence tiers.
Prediction feature vector: 337 columns assembled from 8 Silver sources via left joins on [team, season, week].
ML models: XGBoost spread + over/under with walk-forward CV, Optuna tuning, sealed 2024 holdout.
Tests: 482 passing across 15 test files.

Existing documentation:
- `CLAUDE.md` — project reference, commands, architecture
- `docs/NFL_DATA_DICTIONARY.md` — table definitions for all 15+ Bronze types
- `docs/NFL_GAME_PREDICTION_DATA_MODEL.md` — ML prediction model design
- `docs/NFL_DATA_MODEL_IMPLEMENTATION_GUIDE.md` — implementation roadmap
- `docs/BRONZE_LAYER_DATA_INVENTORY.md` — bronze inventory (auto-generated)

## Constraints

- **Data source**: nfl-data-py is the primary API; some functions have quirks (e.g., `import_rosters` vs `import_seasonal_rosters`)
- **Storage**: Local-first (data/bronze/, data/silver/, data/gold/) with S3 as optional fallback
- **Seasons**: Player data 2020-2025; schedules back to 1999; PBP back to 2016; most types 2016-2025
- **Python**: 3.9 compatible; pandas/pyarrow for all processing

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Local-first storage | AWS credentials expired March 2026 | ✓ Good — fast iteration |
| nfl-data-py as primary source | Battle-tested, covers 95% of needed data | ✓ Good |
| Parquet format | Columnar, compressed, pandas-native | ✓ Good |
| Registry dispatch pattern | Adding a data type is config-only | ✓ Good |
| Adapter pattern (NFLDataAdapter) | Isolates nfl-data-py for future migration | ✓ Good |
| 103 PBP columns (not ~80) | All EPA/WPA/CPOE variants needed for prediction | ✓ Good |
| Warn-never-block validation | Bronze accepts raw data; validation is informational | ✓ Good |
| QBR frequency-prefixed filenames | Prevents weekly/seasonal collision | ✓ Good |
| No row counts in inventory | Too slow for large datasets | ✓ Good |
| stats_player adapter for 2025 | nflverse deprecated old player_stats tag | ✓ Good |
| Week partition registry flag | Automatic per-week file splitting (snap_counts) | ✓ Good |
| Batch ingestion with skip-existing | Idempotent reruns, graceful failure handling | ✓ Good |
| Dry-run default for cleanup scripts | Safe filesystem operations | ✓ Good |
| Rolling windows for team metrics | In-season predictions need recency; season aggregates miss momentum | ✓ Good |
| Separate team_analytics.py module | Protects existing player_analytics.py test suite | ✓ Good |
| Three-tier join for advanced profiles | GSIS ID (NGS), name+team (PFR/QBR), team-only (blitz) | ✓ Good |
| Static dimension table for historical | No season/week partition; avoids row explosion | ✓ Good |
| Lagged SOS (week N-1 only) | Avoids circular dependency in opponent-adjusted EPA | ✓ Good |
| PBP expanded to 140 columns | Penalty, ST, fumble recovery, drive fields needed for v1.3 metrics | ✓ Good |
| STADIUM_ID_COORDS dict (not CSV) | Config lookup matches nflverse stadium_id strings directly | ✓ Good |
| Turnover luck uses expanding window | Regression-to-mean needs full-season context, not 3-game rolling | ✓ Good |
| Referee tendencies from schedules referee col | Simpler than joining Officials Bronze; crew chief name sufficient | ✓ Good |
| Playoff context with simple proxy | Cumulative W-L-T + division rank captures 95% of elimination signal | ✓ Good |
| Game context per-game facts (no rolling) | Weather/rest/travel are single-game properties, not trends | ✓ Good |
| XGBoost over LightGBM/CatBoost | Simplest gradient boosting, proven on tabular NFL data | ✓ Good |
| Walk-forward CV (train 1..N, validate N+1) | Respects temporal ordering; no future leakage | ✓ Good |
| Sealed 2024 holdout | Never touched during tuning; honest final evaluation | ✓ Good |
| Conservative default hyperparameters | Shallow trees (max_depth=4), strong L1/L2 regularization, early stopping | ✓ Good |
| Confidence tiers at 3.0/1.5 thresholds | Simple, interpretable edge buckets for user filtering | ✓ Good |
| Vig-adjusted profit at -110 odds | Standard sportsbook vig; realistic profit accounting | ✓ Good |

## Current Milestone: v2.0 Prediction Model Improvement

**Goal:** Improve ATS accuracy from 53% baseline to 55%+ through better features, model diversity, and signal extraction.

**Baseline (post-leakage fix):**
- ATS: 53.2% overall, 50.0% sealed 2024 holdout
- O/U: 51.9% overall (below 52.38% break-even)
- 283 features, ~2,100 training games, XGBoost only

**Target:**
- ATS: 55%+ overall, 53%+ on holdout
- Profitable at -110 vig on holdout season
- Reduced feature set with better signal-to-noise

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-25 after Phase 29 (Feature Selection) completed*
