# NFL Data Engineering Platform

## What This Is

A comprehensive NFL data engineering platform built on Medallion Architecture (Bronze/Silver/Gold) that powers both fantasy football projections and game outcome predictions. Features 15 Bronze data types with 10 years of history (2016-2025), a rich Silver layer with 11 output paths covering PBP-derived team metrics, game context (weather, rest, travel, coaching), referee tendencies, playoff context, advanced player profiles, and historical dimensions — all assembled into a 337-column prediction feature vector — plus registry-driven ingestion, batch orchestration, and local-first storage.

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

### Active

- ✓ Comprehensive docs refresh (data dictionary for all layers, update stale docs, CLAUDE.md) — Validated in Phase 24
- ✓ ML prediction model (XGBoost) for point spreads using 337-column feature vector — Validated in Phase 25
- ✓ ML prediction model (XGBoost) for over/unders using 337-column feature vector — Validated in Phase 25
- ✓ Backtest ML models against historical closing lines to find market edges — Validated in Phase 26
- [ ] Weekly prediction pipeline generating own lines with edge detection vs Vegas

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

Shipped v1.3 with 20,642 LOC Python across 23 phases and 42 plans (four milestones).
Tech stack: Python 3.9, pandas, pyarrow, pytz, nfl-data-py, local Parquet storage (S3 optional).
Bronze layer: 15 data types covering schedules, player stats, PBP (140 cols), NGS, PFR, QBR, depth charts, combine, draft picks, teams, injuries, rosters, snap counts, officials — 517 files, 93 MB.
Silver layer: team metrics (EPA, tendencies, SOS, situational, PBP-derived 11 metrics, game context, referee tendencies, playoff context), player metrics (usage, rolling avgs, opp rankings, advanced profiles), historical dimension table — 11 output paths.
Gold layer: weekly + preseason projections with injury adjustments, regression shrinkage, floor/ceiling.
Prediction feature vector: 337 columns assembled from 8 Silver sources via left joins on [team, season, week].
Tests: 426 passing across 12 test files.

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

## Current Milestone: v1.4 ML Game Prediction

**Goal:** Build ML models that predict point spreads and over/unders with edges against Vegas closing lines.

**Target features:**
- Comprehensive docs refresh (data dictionary, implementation guide, CLAUDE.md)
- XGBoost/LightGBM spread prediction model trained on 337-column feature vector
- Over/under prediction model
- Backtesting framework comparing model lines vs historical closing lines
- Weekly prediction pipeline with edge detection

---
*Last updated: 2026-03-21 after Phase 26 (backtesting-and-validation) completed*
