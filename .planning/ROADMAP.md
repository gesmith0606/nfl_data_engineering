# Roadmap: NFL Data Engineering Platform

## Milestones

- v1.0 Bronze Expansion -- Phases 1-7 (shipped 2026-03-08)
- v1.1 Bronze Backfill -- Phases 8-14 (shipped 2026-03-13)
- v1.2 Silver Expansion -- Phases 15-19 (shipped 2026-03-15)
- v1.3 Prediction Data Foundation -- Phases 20-23 (shipped 2026-03-19)
- v1.4 ML Game Prediction -- Phases 24-27 (shipped 2026-03-22)
- v2.0 Prediction Model Improvement -- Phases 28-31 (in progress)

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

### v2.0 Prediction Model Improvement (In Progress)

**Milestone Goal:** Improve ATS accuracy from 53% baseline to 55%+ through player-level features, model diversity, feature selection, and advanced signal extraction.

- [x] **Phase 28: Infrastructure & Player Features** - Commit leakage fix, install new dependencies, build QB quality and injury impact features at team-game grain with verified lag guards (completed 2026-03-25)
- [ ] **Phase 29: Feature Selection** - Reduce ~310 features to 80-120 via walk-forward-safe correlation filtering and SHAP importance pruning
- [ ] **Phase 30: Model Ensemble** - Train LightGBM and CatBoost base learners with Ridge meta-learner stacking on temporal OOF predictions, backtest against v1.4 baseline
- [ ] **Phase 31: Advanced Features & Final Validation** - Add momentum signals and adaptive EWM windows, validate marginal improvement, run final holdout comparison

## Phase Details

### Phase 28: Infrastructure & Player Features
**Goal**: The prediction system has player-level signal (QB quality differential, positional injury impact) integrated into its feature vector with verified lag guards and no same-week leakage
**Depends on**: Nothing (first phase of v2.0)
**Requirements**: INFRA-01, INFRA-02, PLAYER-01, PLAYER-02, PLAYER-03, PLAYER-04, PLAYER-05
**Success Criteria** (what must be TRUE):
  1. The leakage fix (same-week raw stat exclusion) is committed and all 439 existing tests pass with it applied
  2. LightGBM, CatBoost, and SHAP import successfully in the project venv on Python 3.9
  3. Running feature assembly produces a feature vector with QB quality differential, backup QB flag, positional injury impact, and RB/WR/OL quality columns at [team, season, week] grain
  4. A test asserts that every player-derived feature uses shift(1) lag -- no game's player features reference that same game's stats
  5. Feature count grows from 283 to approximately 310-330 with the new player columns present in the assembled matrix
**Plans**: 2 plans

Plans:
- [x] 28-01-PLAN.md — Infrastructure: verify leakage fix, install LightGBM/CatBoost/SHAP
- [x] 28-02-PLAN.md — Player quality Silver source: QB EPA, starter detection, injury impact, positional quality with lag guards

### Phase 29: Feature Selection
**Goal**: The feature set is reduced from ~310 to 80-120 high-signal features through walk-forward-safe selection that never touches the 2024 holdout
**Depends on**: Phase 28
**Requirements**: FSEL-01, FSEL-02, FSEL-03, FSEL-04
**Success Criteria** (what must be TRUE):
  1. Running feature selection produces a FeatureSelectionResult with 80-120 selected features and metadata showing which were dropped and why (correlation vs low importance)
  2. No pair of features in the selected set has Pearson correlation exceeding 0.90
  3. Feature selection runs inside each walk-forward CV fold using only that fold's training data -- a test verifies no full-dataset selection occurs
  4. A test asserts that 2024 season data is excluded from all feature selection operations
**Plans**: TBD

Plans:
- [ ] 29-01: TBD
- [ ] 29-02: TBD

### Phase 30: Model Ensemble
**Goal**: A three-model stacking ensemble (XGBoost + LightGBM + CatBoost with Ridge meta-learner) is trained on the reduced feature set and backtested against the v1.4 single-XGBoost baseline
**Depends on**: Phase 29
**Requirements**: ENS-01, ENS-02, ENS-03, ENS-04, ENS-05
**Success Criteria** (what must be TRUE):
  1. LightGBM and CatBoost base learners train with model-specific Optuna search spaces (separate from XGBoost's)
  2. OOF predictions are generated from walk-forward CV folds where no base model trained on future data generates predictions for past games
  3. The Ridge meta-learner trains on temporal OOF predictions and produces ensemble spread and total predictions
  4. Running the backtest CLI with --ensemble produces a side-by-side ATS/ROI comparison vs the v1.4 single-XGBoost baseline
  5. Model artifacts save to models/ensemble/ with metadata.json that the prediction CLI dispatches on automatically
**Plans**: TBD

Plans:
- [ ] 30-01: TBD
- [ ] 30-02: TBD

### Phase 31: Advanced Features & Final Validation
**Goal**: Momentum and adaptive window signals are integrated, their marginal value is measured, and the final model is evaluated on the sealed 2024 holdout with honest comparison to v1.4
**Depends on**: Phase 30
**Requirements**: ADV-01, ADV-02, ADV-03
**Success Criteria** (what must be TRUE):
  1. Momentum features (win streak, ATS trend) derived from schedule data are present in the feature vector with shift(1) lag
  2. Adaptive EWM windows (halflife-based) are computed alongside fixed rolling windows and available as candidate features
  3. A holdout evaluation documents whether advanced features improve, match, or degrade ATS accuracy versus the Phase 30 ensemble
  4. A final comparison table shows v1.4 baseline vs v2.0 best configuration on sealed 2024 holdout: ATS accuracy, O/U accuracy, MAE, and vig-adjusted profit at -110
**Plans**: TBD

Plans:
- [ ] 31-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 28 -> 29 -> 30 -> 31

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Infrastructure Prerequisites | v1.0 | 2/2 | Complete | 2026-03-08 |
| 2. Core PBP Ingestion | v1.0 | 1/1 | Complete | 2026-03-08 |
| 3. Advanced Stats & Context Data | v1.0 | 2/2 | Complete | 2026-03-08 |
| 4. Documentation Update | v1.0 | 3/3 | Complete | 2026-03-08 |
| 5. Phase 1 Verification Backfill | v1.0 | 1/1 | Complete | 2026-03-08 |
| 6. Wire Bronze Validation | v1.0 | 1/1 | Complete | 2026-03-08 |
| 7. Tech Debt Cleanup | v1.0 | 1/1 | Complete | 2026-03-08 |
| 8. Pre-Backfill Guards | v1.1 | 1/1 | Complete | 2026-03-09 |
| 9. New Data Type Ingestion | v1.1 | 3/3 | Complete | 2026-03-09 |
| 10. Existing Type Backfill | v1.1 | 2/2 | Complete | 2026-03-12 |
| 11. Orchestration and Validation | v1.1 | 2/2 | Complete | 2026-03-12 |
| 12. 2025 Player Stats Gap Closure | v1.1 | 2/2 | Complete | 2026-03-13 |
| 13. Bronze-Silver Path Alignment | v1.1 | 1/1 | Complete | 2026-03-13 |
| 14. Bronze Cosmetic Cleanup | v1.1 | 1/1 | Complete | 2026-03-13 |
| 15. PBP Team Metrics and Tendencies | v1.2 | 3/3 | Complete | 2026-03-14 |
| 16. Strength of Schedule and Situational Splits | v1.2 | 2/2 | Complete | 2026-03-14 |
| 17. Advanced Player Profiles | v1.2 | 2/2 | Complete | 2026-03-14 |
| 18. Historical Context | v1.2 | 2/2 | Complete | 2026-03-15 |
| 19. v1.2 Tech Debt Cleanup | v1.2 | 1/1 | Complete | 2026-03-15 |
| 20. Infrastructure and Data Expansion | v1.3 | 2/2 | Complete | 2026-03-16 |
| 21. PBP-Derived Team Metrics | v1.3 | 3/3 | Complete | 2026-03-16 |
| 22. Schedule-Derived Context | v1.3 | 2/2 | Complete | 2026-03-17 |
| 23. Cross-Source Features and Integration | v1.3 | 2/2 | Complete | 2026-03-19 |
| 24. Documentation Refresh | v1.4 | 2/2 | Complete | 2026-03-21 |
| 25. Feature Assembly and Model Training | v1.4 | 3/3 | Complete | 2026-03-21 |
| 26. Backtesting and Validation | v1.4 | 2/2 | Complete | 2026-03-21 |
| 27. Prediction Pipeline | v1.4 | 1/1 | Complete | 2026-03-22 |
| 28. Infrastructure & Player Features | v2.0 | 2/2 | Complete    | 2026-03-25 |
| 29. Feature Selection | v2.0 | 0/2 | Not started | - |
| 30. Model Ensemble | v2.0 | 0/2 | Not started | - |
| 31. Advanced Features & Final Validation | v2.0 | 0/1 | Not started | - |

---
*Roadmap created: 2026-03-08*
*Last updated: 2026-03-24 after Phase 28 planning*
