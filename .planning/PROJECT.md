# NFL Data Engineering Platform

## What This Is

A comprehensive NFL data engineering platform built on Medallion Architecture (Bronze/Silver/Gold) that powers both fantasy football projections and ML game outcome predictions. Features 16 Bronze data types (including historical odds) with 10 years of history (2016-2025), a rich Silver layer with 12 output paths (including market/line movement data), a 310+ column prediction feature vector, an XGB+LGB+CB+Ridge stacking ensemble for point spread and over/under prediction with walk-forward cross-validation, closing line value (CLV) tracking for model evaluation, backtesting against historical Vegas closing lines, and a weekly prediction pipeline with edge detection and confidence tiers — plus registry-driven ingestion, batch orchestration, and local-first storage.

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
- ✓ Momentum features (win streak, ATS trend/margin) and EWM windows (halflife=3) for team metrics — Phase 31, v2.0
- ✓ Ablation: Phase 31 features improved training but did not improve holdout; P30 ensemble confirmed as v2.0 — Phase 31, v2.0
- ✓ Final holdout: v1.4 (50.0% ATS, -$12.18) → v2.0 ensemble (53.0% ATS, +$3.09) on sealed 2024 — Phase 31, v2.0
- ✓ 503 total tests passing — v2.0
- ✓ Bronze odds ingestion: FinnedAI JSON → Parquet with 45-entry team mapping, sign convention alignment, nflverse join (r=0.997 cross-validation), zero orphans — Phase 32, v2.1
- ✓ 516 total tests passing — v2.1
- ✓ Silver line movement features: spread/total shift, ordinal magnitude buckets, key number crossings, per-team reshape with sign flips, feature_engineering.py integration (opening_spread/opening_total in _PRE_GAME_CONTEXT) — Phase 33, v2.1
- ✓ 545 total tests passing — v2.1
- ✓ CLV tracking: evaluate_clv(), by-tier, by-season metrics in prediction backtester and CLI — Phase 34, v2.1
- ✓ Market feature ablation script: P30 baseline vs market-augmented ensemble on sealed 2024 holdout with SHAP report and ship-or-skip verdict — Phase 34, v2.1
- ✓ 571 total tests passing — v2.1
- ✓ Full FinnedAI odds ingestion for all 6 seasons (2016-2021) with cross-validation r > 0.95, nflverse odds bridge for 2022-2025 with line_source provenance — Phase 35, v2.2
- ✓ 2025 Bronze data complete (7/8 types; injuries capped at 2024 by nflverse) with 285 games confirmed — Phase 35, v2.2
- ✓ 594 total tests passing — v2.2
- ✓ Silver market data for all 10 seasons (2016-2025) with line movement features; player quality gap-filled (2020-2025) — Phase 36, v2.2
- ✓ 2025 feature vector: 272 REG games, 1139 columns, 0% NaN on market features; training seasons 2016-2024 all assemble correctly — Phase 36, v2.2
- ✓ Holdout rotated to 2025 with derived season ranges; ensemble retrained on 2016-2024; 2025 baseline: 51.7% ATS, -$3.73 profit — Phase 37, v2.2
- ✓ Market feature ablation: SHIP — 50.6% ATS beats 50.2% baseline (+0.4%); diff_opening_spread is #1 SHAP feature (23.6%); 120-feature SHAP-selected ensemble promoted to production — Phase 38, v2.2
- ✓ Player-week feature vector assembly: 9 Silver sources joined into per-player-per-week rows (5,480 rows, 337 features for 2024), shift(1) temporal lag enforcement, matchup features, Vegas implied totals, leakage detection — Phase 39, v3.0
- ✓ 608 total tests passing — v3.0
- ✓ Per-position per-stat XGBoost models (19 total: QB 5, RB 6, WR 4, TE 4) with walk-forward CV (3 expanding folds), SHAP feature selection per stat-type group, ship gate with dual agreement (OOF + holdout) — Phase 40, v3.0
- ✓ 622 total tests passing — v3.0

### Active

- [ ] Opportunity and efficiency decomposition for player predictions
- [ ] Matchup-aware adjustments using existing Silver data
- [ ] Game-level constraints (team total allocation)

## Current Milestone: v3.0 Player Fantasy Prediction System

**Goal:** Replace heuristic player projections with ML-based models that produce the most accurate fantasy point predictions per position.

**Target features:**
- Position-specific ML models trained on historical player performance
- Opportunity/efficiency decomposition (snap share, target share, rush attempts, efficiency metrics)
- Matchup context integration from existing Silver layer
- Game-level constraints (implied team totals, game script)
- Evaluation framework with per-position MAE/RMSE/correlation benchmarks
- Walk-forward CV respecting temporal ordering (same patterns as game prediction)

### Planned (Future Milestones)

**Player prediction path (priority):**
- v3.0 Player Fantasy Prediction System — opportunity models, efficiency models, matchup context, game-level constraints, regime detection, evaluation framework
- v3.1 Graph-Enhanced Predictions — Neo4j foundation, WR-CB matchups, target networks, graph features into both game and player models

**Production & delivery path:**
- v4.0 Production Pipeline — automated weekly runs, drift detection, monitoring
- v4.1 Web MVP — FastAPI backend + frontend, projections + lines display
- v4.2 User Accounts + Sleeper — OAuth, team linking, roster import, lineup advice
- v4.3 Fantasy Agent — LLM-powered start/sit, waiver recommendations
- v4.4 Draft Agent — real-time draft tracking + pick recommendations (Sleeper-first)
- v5.0 Multi-Platform — ESPN/Yahoo draft support

### Out of Scope

- S3 sync — AWS credentials expired, local-first workflow active
- nflreadpy migration — requires Python 3.10+; separate future milestone
- Neural networks / deep learning — gradient boosting dominates tabular sports prediction at this data scale
- Real-time prediction serving — batch weekly predictions sufficient

## Context

Shipped v2.2 with ~33,000 LOC Python across 38 phases and 71 plans (eight milestones).
Tech stack: Python 3.9, pandas, pyarrow, pytz, xgboost, lightgbm, catboost, scikit-learn, optuna, shap, nfl-data-py, local Parquet storage (S3 optional).
Bronze layer: 16 data types + odds (FinnedAI 2016-2021, nflverse bridge 2022-2025) covering 10 seasons of complete data.
Silver layer: 13 team output paths (including market/line movement data for all 10 seasons), 3 player output paths, historical dimension table.
Gold layer: weekly + preseason fantasy projections; ML game predictions with 120-feature SHAP-selected ensemble (market features included).
Prediction feature vector: 1139 raw columns → 120 SHAP-selected features. `diff_opening_spread` is #1 feature (23.6% SHAP importance).
ML models: v2.2 stacking ensemble (XGB+LGB+CB + Ridge meta-learner) with market features; walk-forward CV, sealed 2025 holdout (51.7% ATS, 50.6% with market features). CLV tracking measures model quality against closing lines.
Player models: 19 per-position per-stat XGBoost models (walk-forward CV, SHAP feature selection per stat-type group, ship gate evaluation).
Tests: 622 passing across 21 test files.

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
| XGBoost as initial model | Simplest gradient boosting, proven on tabular NFL data | ✓ Good — later expanded to ensemble |
| Walk-forward CV (train 1..N, validate N+1) | Respects temporal ordering; no future leakage | ✓ Good |
| Sealed 2024 holdout | Never touched during tuning; honest final evaluation | ✓ Good |
| Conservative default hyperparameters | Shallow trees (max_depth=4), strong L1/L2 regularization, early stopping | ✓ Good |
| Confidence tiers at 3.0/1.5 thresholds | Simple, interpretable edge buckets for user filtering | ✓ Good |
| Vig-adjusted profit at -110 odds | Standard sportsbook vig; realistic profit accounting | ✓ Good |
| XGB+LGB+CB stacking with Ridge | Model diversity improves generalization over single XGBoost | ✓ Good — +3% ATS on holdout |
| SHAP-based feature selection | Walk-forward-safe, per-fold isolation, holdout excluded | ✓ Good — 310→100 features |
| Honest ablation for Phase 31 features | Momentum/EWM improved training but not holdout | ✓ Good — shipped P30 ensemble |
| Conservative hyperparameters for LGB/CB | Analogous to XGBoost: shallow trees, strong regularization | ✓ Good |
| CLV = predicted_margin - spread_line | Point-based CLV is the gold standard for betting model evaluation | ✓ Good |
| Ablation saves to models/ensemble_ablation/ | Protects production model during comparison | ✓ Good |
| Ship market features only if holdout ATS improves | Accuracy is the decision criterion, not model purity | ✓ Good |
| FinnedAI JSON (not SBRO XLSX) for odds | JSON simpler to parse, same data, no openpyxl dep needed | ✓ Good |
| 45-entry hardcoded team mapping | Explicit and auditable vs fuzzy matching; covers all FinnedAI names | ✓ Good |
| Negate FinnedAI spreads for nflverse convention | Positive = home favored; one-line transform avoids confusion | ✓ Good |
| Ordinal float64 for magnitude buckets | Survives numeric dtype filter in feature_engineering.py | ✓ Good |
| Opening lines only in _PRE_GAME_CONTEXT | Closing-line-derived features are retrospective (leakage) | ✓ Good |
| CLV uses nflverse spread_line (not FinnedAI) | nflverse has full season coverage; FinnedAI only 2016-2021 | ✓ Good |
| nflverse closing lines as opening proxies for 2022+ | Free, 100% coverage, gradient boosting handles approximate values | ✓ Good — 0% NaN on market features |
| line_source provenance column | Distinguishes FinnedAI from nflverse data for downstream filtering | ✓ Good |
| Derived season ranges from HOLDOUT_SEASON | Future holdout rotations are a one-line change | ✓ Good |
| No hyperparameter re-tuning during holdout rotation | Fair baseline comparison; avoids confounding tuning with holdout change | ✓ Good |
| SHAP-based feature selection (321→120 features) | Removes noise, preserves signal; diff_opening_spread confirmed as #1 | ✓ Good |
| Market features SHIP verdict | 50.6% > 50.2% ATS on structurally valid ablation (6 seasons training data) | ✓ Good — definitive answer |

## Previous Milestone: v2.2 Full Odds + Holdout Reset

**Shipped:** 2026-03-29 | **Phases:** 35-38 | **Plans:** 7 | **Delivered:** Full odds coverage (2016-2025), holdout rotated to 2025, market feature ablation SHIP verdict, 120-feature SHAP-selected ensemble

See `.planning/milestones/v2.2-ROADMAP.md` for full archive.

## Previous Milestone: v2.1 Market Data

**Shipped:** 2026-03-28 | **Phases:** 32-34 | **Plans:** 6

See `.planning/milestones/v2.1-ROADMAP.md` for full archive.

## Previous Milestone: v2.0 Prediction Model Improvement

**Shipped:** 2026-03-27 | **Phases:** 28-31 | **Plans:** 8 | **Result:** 53.0% ATS, +$3.09 profit on sealed 2024 holdout

See `.planning/milestones/v2.0-ROADMAP.md` for full archive.

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
*Last updated: 2026-03-31 after Phase 40 complete*
