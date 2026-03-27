# Milestones

## v2.0 Prediction Model Improvement (Shipped: 2026-03-27)

**Phases completed:** 4 phases, 8 plans, 15 tasks

**Key accomplishments:**

- Leakage-safe feature selection committed (337 to 283 features) and LightGBM/CatBoost/SHAP installed for ensemble modeling
- Team-level player quality features (QB EPA, positional quality, injury impact) with shift(1) lag guards and 18 new rolling differential columns for prediction
- SHAP TreeExplainer feature ranking with greedy correlation filter (r > 0.90) and holdout guard, isolated per walk-forward CV fold
- Walk-forward CV cutoff search CLI with SELECTED_FEATURES persistence in config.py and metadata JSON output
- XGBoost+LightGBM+CatBoost stacking with Ridge meta-learner, generalized walk-forward CV producing OOF predictions, and ensemble save/load for spread and total models
- Ensemble training CLI with Optuna tuning, side-by-side ATS/ROI backtest comparison, and --ensemble prediction dispatch for XGB+LGB+CB+Ridge stacking
- Momentum streak/ATS signals from Bronze schedules plus EWM adaptive windows on team EPA/success/CPOE metrics, all with shift(1) leakage prevention
- Three-way sealed holdout comparison (v1.4 vs P30 Ensemble vs P31 Full) confirming P30 Ensemble as v2.0 production model with 53.0% ATS accuracy and +3.09 profit on 2024 holdout

---

## v1.4 ML Game Prediction (Shipped: 2026-03-22)

**Phases completed:** 4 phases, 8 plans, 11 tasks

**Key accomplishments:**

- Complete Silver (12 tables, 719 columns) and Gold (25 + 15 columns) schema documentation extracted from parquet files, replacing 2 aspirational Silver tables with real schemas
- CLAUDE.md refreshed with 15+ Bronze types, 12 Silver paths, 360 tests, v1.3 complete status; implementation guide updated with phases 18-23 completed and 24-27 planned; Bronze inventory regenerated showing PBP at 140 columns and officials data type
- Game-level differential feature assembly from 8 Silver team sources producing 272 REG game rows with 322 diff_ columns and 337 total features per season
- Walk-forward CV framework with 5 season-boundary folds and XGBoost model training with JSON serialization and 2024 holdout guard
- Training CLI with Optuna TPE tuning (50 trials), --no-tune conservative defaults, and gain-based feature importance report (top 20 console + CSV)
- ATS and O/U evaluation library with vig-adjusted profit accounting at -110 odds, plus CLI for running backtests against historical Vegas closing lines
- Sealed 2024 holdout evaluation with leakage guard plus per-season ATS stability analysis with 58% leakage threshold warning
- Weekly prediction pipeline with edge detection vs Vegas lines, confidence tiers (high/medium/low at 3.0/1.5 thresholds), and Gold Parquet output

---

## v1.3 Prediction Data Foundation (Shipped: 2026-03-19)

**Phases completed:** 4 phases, 9 plans, 23 requirements
**Commits:** 61 | **LOC:** 20,642 Python | **Tests:** 360 passing (71 new)

**Key accomplishments:**

- Expanded PBP Bronze to 140 columns (penalty, ST, fumble recovery, drives) and ingested officials data for 2016-2025
- Built 11 PBP-derived team metrics (penalties, turnovers, red zone trips, FG accuracy, punt/kick returns, 3rd down, explosives, drive efficiency, sack rates, TOP) with rolling windows in Silver
- Created game_context Silver module with weather, rest/travel distance, timezone differential, and coaching tenure features
- Computed referee tendency profiles (expanding-window penalty rates per crew) and playoff/elimination context (W-L-T standings, division rank, games behind, contention flag)
- Assembled 337-column prediction feature vector from 8 Silver sources via left joins on [team, season, week]
- Pipeline health monitoring expanded to cover all 11 Silver output paths

---

## v1.2 Silver Expansion (Shipped: 2026-03-15)

**Phases completed:** 5 phases, 10 plans, 25 requirements
**Commits:** 60 | **LOC:** 16,821 Python | **Tests:** 289 passing (103 new)

**Key accomplishments:**

- PBP-derived team performance metrics (EPA, success rate, CPOE, red zone efficiency) and tendencies (pace, PROE, 4th-down aggressiveness) with 3/6-game rolling windows
- Opponent-adjusted EPA with lagged schedule difficulty rankings (1-32) and situational splits (home/away, divisional, game script) with rolling windows
- Advanced player profiles from NGS/PFR/QBR data (separation, RYOE, TTT, pressure, blitz, QBR) with three-tier join strategy across 47K+ player-weeks
- Historical dimension table with combine measurables (speed score, burst, catch radius) and Jimmy Johnson draft chart values for 9,892 players
- Pipeline health monitoring for all 7 Silver paths, config-driven S3 keys, and tech debt cleanup closing all audit gaps

---

## v1.1 Bronze Backfill (Shipped: 2026-03-13)

**Phases completed:** 7 phases, 12 plans, 0 tasks

**Commits:** 50+ | **LOC:** 12,084 Python | **Tests:** 186 passing

**Key accomplishments:**

- Ingested 9 new Bronze data types (PBP, NGS, PFR, QBR, depth charts, draft picks, combine, teams) with full historical coverage
- Backfilled 6 existing types from 2020-2024 to 2016-2025 range (517 files, 93 MB total)
- Built batch ingestion CLI with progress reporting, failure handling, and skip-existing deduplication
- Implemented stats_player adapter for 2025 data via nflverse's new release tag with column mapping
- Fixed Bronze-Silver path alignment for snap_counts and schedules, ensuring end-to-end pipeline
- Complete Bronze inventory: 15 data types, 10 years of history, all passing validate_data()

---

## v1.0 Bronze Expansion (Shipped: 2026-03-08)

**Phases completed:** 7 phases, 11 plans, 0 tasks

**Commits:** 81 | **LOC:** 10,095 Python | **Tests:** 70 milestone-specific

**Key accomplishments:**

- Registry-driven Bronze CLI with 15+ data types via config-only dispatch, local-first storage
- Full PBP ingestion — 103 curated columns (EPA/WPA/CPOE/air yards) for 2010-2025
- Advanced stats expansion — NGS, PFR weekly/seasonal, QBR, depth charts, draft picks, combine
- Complete documentation — data dictionary, inventory script, prediction model badges, implementation guide
- Bronze validation pipeline — validate_data() wired into ingestion with warn-never-block pattern
- 70 milestone-specific tests across infrastructure, PBP, advanced stats, inventory, and validation

---
