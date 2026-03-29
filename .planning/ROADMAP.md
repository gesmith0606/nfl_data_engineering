# Roadmap: NFL Data Engineering Platform

## Milestones

- v1.0 Bronze Expansion -- Phases 1-7 (shipped 2026-03-08)
- v1.1 Bronze Backfill -- Phases 8-14 (shipped 2026-03-13)
- v1.2 Silver Expansion -- Phases 15-19 (shipped 2026-03-15)
- v1.3 Prediction Data Foundation -- Phases 20-23 (shipped 2026-03-19)
- v1.4 ML Game Prediction -- Phases 24-27 (shipped 2026-03-22)
- v2.0 Prediction Model Improvement -- Phases 28-31 (shipped 2026-03-27)
- v2.1 Market Data -- Phases 32-34 (shipped 2026-03-28)
- **v2.2 Full Odds + Holdout Reset** -- Phases 35-38 (in progress)

## Phases

<details>
<summary>v1.0 Bronze Expansion (Phases 1-7) -- SHIPPED 2026-03-08</summary>

- [x] Phase 1: Infrastructure Prerequisites (2/2 plans) -- completed 2026-03-08
- [x] Phase 2: Core PBP Ingestion (1/1 plan) -- completed 2026-03-08
- [x] Phase 3: Advanced Stats & Context Data (2/2 plans) -- completed 2026-03-08
- [x] Phase 4: Documentation Update (3/3 plans) -- completed 2026-03-08
- [x] Phase 5: Phase 1 Verification Backfill (1/1 plan) -- completed 2026-03-08
- [x] Phase 6: Wire Bronze Validation (1/1 plan) -- completed 2026-03-08
- [x] Phase 7: Tech Debt Cleanup (1/1 plan) -- completed 2026-03-08

Full details: `.planning/milestones/v1.0-ROADMAP.md`

</details>

<details>
<summary>v1.1 Bronze Backfill (Phases 8-14) -- SHIPPED 2026-03-13</summary>

- [x] Phase 8: Pre-Backfill Guards (1/1 plan) -- completed 2026-03-09
- [x] Phase 9: New Data Type Ingestion (3/3 plans) -- completed 2026-03-09
- [x] Phase 10: Existing Type Backfill (2/2 plans) -- completed 2026-03-12
- [x] Phase 11: Orchestration and Validation (2/2 plans) -- completed 2026-03-12
- [x] Phase 12: 2025 Player Stats Gap Closure (2/2 plans) -- completed 2026-03-13
- [x] Phase 13: Bronze-Silver Path Alignment (1/1 plan) -- completed 2026-03-13
- [x] Phase 14: Bronze Cosmetic Cleanup (1/1 plan) -- completed 2026-03-13

Full details: `.planning/milestones/v1.1-ROADMAP.md`

</details>

<details>
<summary>v1.2 Silver Expansion (Phases 15-19) -- SHIPPED 2026-03-15</summary>

- [x] Phase 15: PBP Team Metrics and Tendencies (3/3 plans) -- completed 2026-03-14
- [x] Phase 16: Strength of Schedule and Situational Splits (2/2 plans) -- completed 2026-03-14
- [x] Phase 17: Advanced Player Profiles (2/2 plans) -- completed 2026-03-14
- [x] Phase 18: Historical Context (2/2 plans) -- completed 2026-03-15
- [x] Phase 19: v1.2 Tech Debt Cleanup (1/1 plan) -- completed 2026-03-15

Full details: `.planning/milestones/v1.2-ROADMAP.md`

</details>

<details>
<summary>v1.3 Prediction Data Foundation (Phases 20-23) -- SHIPPED 2026-03-19</summary>

- [x] Phase 20: Infrastructure and Data Expansion (2/2 plans) -- completed 2026-03-16
- [x] Phase 21: PBP-Derived Team Metrics (3/3 plans) -- completed 2026-03-16
- [x] Phase 22: Schedule-Derived Context (2/2 plans) -- completed 2026-03-17
- [x] Phase 23: Cross-Source Features and Integration (2/2 plans) -- completed 2026-03-19

Full details: `.planning/milestones/v1.3-ROADMAP.md`

</details>

<details>
<summary>v1.4 ML Game Prediction (Phases 24-27) -- SHIPPED 2026-03-22</summary>

- [x] Phase 24: Documentation Refresh (2/2 plans) -- completed 2026-03-21
- [x] Phase 25: Feature Assembly and Model Training (3/3 plans) -- completed 2026-03-21
- [x] Phase 26: Backtesting and Validation (2/2 plans) -- completed 2026-03-21
- [x] Phase 27: Prediction Pipeline (1/1 plan) -- completed 2026-03-22

Full details: `.planning/milestones/v1.4-ROADMAP.md`

</details>

<details>
<summary>v2.0 Prediction Model Improvement (Phases 28-31) -- SHIPPED 2026-03-27</summary>

- [x] Phase 28: Infrastructure & Player Features (2/2 plans) -- completed 2026-03-25
- [x] Phase 29: Feature Selection (2/2 plans) -- completed 2026-03-25
- [x] Phase 30: Model Ensemble (2/2 plans) -- completed 2026-03-26
- [x] Phase 31: Advanced Features & Final Validation (2/2 plans) -- completed 2026-03-27

Full details: `.planning/milestones/v2.0-ROADMAP.md`

</details>

<details>
<summary>v2.1 Market Data (Phases 32-34) -- SHIPPED 2026-03-28</summary>

- [x] Phase 32: Bronze Odds Ingestion (2/2 plans) -- completed 2026-03-27
- [x] Phase 33: Silver Line Movement Features (2/2 plans) -- completed 2026-03-28
- [x] Phase 34: CLV Tracking + Ablation (2/2 plans) -- completed 2026-03-28

Full details: `.planning/milestones/v2.1-ROADMAP.md`

</details>

### v2.2 Full Odds + Holdout Reset (In Progress)

**Milestone Goal:** Complete odds coverage across all available seasons (2016-2025), run the full data pipeline for 2025, rotate the holdout from 2024 to 2025, and deliver the first structurally valid market feature ablation with 6 seasons of training data.

- [x] **Phase 35: Bronze Data Completion** - Ingest remaining FinnedAI seasons, nflverse 2022+ closing lines, and full 2025 Bronze (completed 2026-03-28)
- [x] **Phase 36: Silver and Feature Vector Assembly** - Generate Silver market data for all odds seasons and all Silver transformations for 2025 (completed 2026-03-29)
- [ ] **Phase 37: Holdout Reset and Baseline** - Rotate holdout to 2025, retrain ensemble on 2016-2024, establish sealed baseline
- [ ] **Phase 38: Market Feature Ablation** - Re-run ablation with full market coverage and deliver ship-or-skip verdict

## Phase Details

### Phase 35: Bronze Data Completion
**Goal**: All Bronze odds and 2025 season data exist as validated Parquet files, providing complete raw inputs for Silver transformations
**Depends on**: Nothing (first phase of v2.2)
**Requirements**: BRNZ-01, BRNZ-02, BRNZ-03
**Success Criteria** (what must be TRUE):
  1. Running `bronze_odds_ingestion.py --season YYYY` for each of 2016-2019, 2021 produces validated Parquet with cross-validation r > 0.95 per season
  2. Bronze Parquet files exist for 2022-2025 containing closing spread_line and total_line sourced from nflverse schedules, with a `line_source` column distinguishing them from FinnedAI data
  3. All 8 core Bronze data types (schedules, PBP, player_weekly, player_seasonal, snap_counts, injuries, rosters, teams) are ingested for the 2025 season with validate_data() passing
  4. A smoke test confirms 2025 schedules contain at least 285 regular-season games via nfl-data-py
**Plans**: 2 plans

Plans:
- [x] 35-01: FinnedAI batch ingestion and nflverse odds bridge
- [x] 35-02: 2025 season Bronze ingestion

### Phase 36: Silver and Feature Vector Assembly
**Goal**: Silver market features cover the full 2016-2025 window and 2025 Silver data is complete, enabling feature vector assembly for the new holdout season
**Depends on**: Phase 35
**Requirements**: SLVR-01, SLVR-02, SLVR-03
**Success Criteria** (what must be TRUE):
  1. Silver market_data Parquet exists for all 6 FinnedAI seasons (2016-2021) with line movement features (spread_shift, total_shift, magnitude buckets)
  2. All Silver transformations (player usage, team metrics, game context, advanced profiles, player quality) complete for 2025 with no missing-column errors
  3. Feature vector assembly for 2025 produces game rows with opening_spread and opening_total populated (NaN rate below 5% for games with odds coverage)
  4. Feature vector row count for 2025 matches the number of regular-season games (at least 285 game-team rows)
**Plans**: 2 plans

Plans:
- [x] 36-01: Silver market expansion and 2025 Silver transformations
- [x] 36-02: Feature vector assembly and validation

### Phase 37: Holdout Reset and Baseline
**Goal**: The evaluation framework uses 2025 as the sealed holdout with a documented ensemble baseline, enabling honest model comparison going forward
**Depends on**: Phase 36
**Requirements**: HOLD-01, HOLD-02, HOLD-03
**Success Criteria** (what must be TRUE):
  1. config.py HOLDOUT_SEASON equals 2025 and TRAINING_SEASONS, VALIDATION_SEASONS, PREDICTION_SEASONS are computed automatically from HOLDOUT_SEASON (not hardcoded lists)
  2. Running `train_ensemble.py` trains on 2016-2024 data with the holdout guard rejecting any 2025 data in training folds
  3. Running `backtest_predictions.py --holdout` produces ATS accuracy, profit, and CLV metrics against the sealed 2025 holdout with results documented
  4. All tests that previously hardcoded `2024` as the holdout season now import HOLDOUT_SEASON from config and pass
**Plans**: 2 plans

Plans:
- [ ] 37-01: Holdout config rotation and test updates
- [ ] 37-02: Ensemble retraining and baseline documentation

### Phase 38: Market Feature Ablation
**Goal**: A definitive, structurally valid answer on whether market features improve game prediction accuracy, based on 6 seasons of market training data and a fresh 2025 holdout
**Depends on**: Phase 37
**Requirements**: HOLD-04
**Success Criteria** (what must be TRUE):
  1. Ablation script runs P30 baseline (no market features) vs market-augmented ensemble on the 2025 holdout, with both models trained on 2016-2024
  2. SHAP importance report shows relative contribution of opening_spread and opening_total in the market-augmented model
  3. Ship-or-skip verdict is rendered using the existing gate (strict > on holdout ATS accuracy) and documented with exact metrics
**Plans**: 2 plans

Plans:
- [ ] 38-01: Market ablation execution and verdict

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1-7 | v1.0 | 11/11 | Complete | 2026-03-08 |
| 8-14 | v1.1 | 12/12 | Complete | 2026-03-13 |
| 15-19 | v1.2 | 10/10 | Complete | 2026-03-15 |
| 20-23 | v1.3 | 9/9 | Complete | 2026-03-19 |
| 24-27 | v1.4 | 8/8 | Complete | 2026-03-22 |
| 28-31 | v2.0 | 8/8 | Complete | 2026-03-27 |
| 32-34 | v2.1 | 6/6 | Complete | 2026-03-28 |
| 35. Bronze Data Completion | v2.2 | 2/2 | Complete    | 2026-03-28 |
| 36. Silver + Feature Vector | v2.2 | 2/2 | Complete    | 2026-03-29 |
| 37. Holdout Reset + Baseline | v2.2 | 0/2 | Not started | - |
| 38. Market Ablation | v2.2 | 0/1 | Not started | - |

---
*Roadmap created: 2026-03-08*
*Last updated: 2026-03-28 after v2.2 roadmap creation*
