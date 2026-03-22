# Roadmap: NFL Data Engineering Platform

## Milestones

- ✅ **v1.0 Bronze Expansion** — Phases 1-7 (shipped 2026-03-08)
- ✅ **v1.1 Bronze Backfill** — Phases 8-14 (shipped 2026-03-13)
- ✅ **v1.2 Silver Expansion** — Phases 15-19 (shipped 2026-03-15)
- ✅ **v1.3 Prediction Data Foundation** — Phases 20-23 (shipped 2026-03-19)
- 📋 **v1.4 ML Game Prediction** — Phases 24-27 (in progress)

## Phases

<details>
<summary>✅ v1.0 Bronze Expansion (Phases 1-7) — SHIPPED 2026-03-08</summary>

- [x] Phase 1: Infrastructure Prerequisites (2/2 plans) — completed 2026-03-08
- [x] Phase 2: Core PBP Ingestion (1/1 plan) — completed 2026-03-08
- [x] Phase 3: Advanced Stats & Context Data (2/2 plans) — completed 2026-03-08
- [x] Phase 4: Documentation Update (3/3 plans) — completed 2026-03-08
- [x] Phase 5: Phase 1 Verification Backfill (1/1 plan) — completed 2026-03-08
- [x] Phase 6: Wire Bronze Validation (1/1 plan) — completed 2026-03-08
- [x] Phase 7: Tech Debt Cleanup (1/1 plan) — completed 2026-03-08

Full details: `.planning/milestones/v1.0-ROADMAP.md`

</details>

<details>
<summary>✅ v1.1 Bronze Backfill (Phases 8-14) — SHIPPED 2026-03-13</summary>

- [x] Phase 8: Pre-Backfill Guards (1/1 plan) — completed 2026-03-09
- [x] Phase 9: New Data Type Ingestion (3/3 plans) — completed 2026-03-09
- [x] Phase 10: Existing Type Backfill (2/2 plans) — completed 2026-03-12
- [x] Phase 11: Orchestration and Validation (2/2 plans) — completed 2026-03-12
- [x] Phase 12: 2025 Player Stats Gap Closure (2/2 plans) — completed 2026-03-13
- [x] Phase 13: Bronze-Silver Path Alignment (1/1 plan) — completed 2026-03-13
- [x] Phase 14: Bronze Cosmetic Cleanup (1/1 plan) — completed 2026-03-13

Full details: `.planning/milestones/v1.1-ROADMAP.md`

</details>

<details>
<summary>✅ v1.2 Silver Expansion (Phases 15-19) — SHIPPED 2026-03-15</summary>

- [x] Phase 15: PBP Team Metrics and Tendencies (3/3 plans) — completed 2026-03-14
- [x] Phase 16: Strength of Schedule and Situational Splits (2/2 plans) — completed 2026-03-14
- [x] Phase 17: Advanced Player Profiles (2/2 plans) — completed 2026-03-14
- [x] Phase 18: Historical Context (2/2 plans) — completed 2026-03-15
- [x] Phase 19: v1.2 Tech Debt Cleanup (1/1 plan) — completed 2026-03-15

Full details: `.planning/milestones/v1.2-ROADMAP.md`

</details>

<details>
<summary>✅ v1.3 Prediction Data Foundation (Phases 20-23) — SHIPPED 2026-03-19</summary>

- [x] Phase 20: Infrastructure and Data Expansion (2/2 plans) — completed 2026-03-16
- [x] Phase 21: PBP-Derived Team Metrics (3/3 plans) — completed 2026-03-16
- [x] Phase 22: Schedule-Derived Context (2/2 plans) — completed 2026-03-17
- [x] Phase 23: Cross-Source Features and Integration (2/2 plans) — completed 2026-03-19

Full details: `.planning/milestones/v1.3-ROADMAP.md`

</details>

### v1.4 ML Game Prediction (In Progress)

**Milestone Goal:** Build ML models that predict NFL point spreads and over/unders, backtest against historical closing lines, and generate weekly predictions with edge detection vs Vegas.

- [x] **Phase 24: Documentation Refresh** - Update all project docs to reflect v1.3 completion and v1.4 architecture (completed 2026-03-21)
- [x] **Phase 25: Feature Assembly and Model Training** - Build game-level differential features and train XGBoost spread/total models with walk-forward CV (completed 2026-03-21)
- [x] **Phase 26: Backtesting and Validation** - Validate models against historical closing lines with ATS accuracy and profit analysis (completed 2026-03-21)
- [x] **Phase 27: Prediction Pipeline** - Weekly prediction generation with edge detection and confidence scoring vs Vegas lines (completed 2026-03-22)

## Phase Details

### Phase 24: Documentation Refresh
**Goal**: All project documentation accurately reflects the current state of the platform after four milestones
**Depends on**: Nothing (opening phase, no code dependencies)
**Requirements**: DOCS-01, DOCS-02, DOCS-03, DOCS-04, DOCS-05
**Success Criteria** (what must be TRUE):
  1. Data dictionary contains schema definitions and column descriptions for all 11 Silver output paths
  2. Data dictionary contains Gold layer prediction output schema (even if prediction tables do not yet exist, the planned schema is documented)
  3. CLAUDE.md reflects current architecture (15 Bronze types, 11 Silver paths, 360 tests, v1.3 status)
  4. Implementation guide shows v1.3 phases as complete with current prediction model status badges
  5. Bronze inventory shows PBP at 140 columns and includes officials data type
**Plans**: 2 plans

Plans:
- [x] 24-01: Silver and Gold data dictionary updates
- [x] 24-02: CLAUDE.md, implementation guide, and Bronze inventory refresh

### Phase 25: Feature Assembly and Model Training
**Goal**: XGBoost models for spread and over/under prediction trained on properly assembled game-level differential features with walk-forward cross-validation
**Depends on**: Phase 24
**Requirements**: FEAT-01, FEAT-02, FEAT-03, FEAT-04, MODL-01, MODL-02, MODL-03, MODL-04, MODL-05
**Success Criteria** (what must be TRUE):
  1. Running `python scripts/train_prediction_model.py --target spread` produces a saved model file that can predict point spreads for any game given two team names and a season/week
  2. Running `python scripts/train_prediction_model.py --target total` produces a saved over/under model with the same interface
  3. Every feature used for week N predictions comes exclusively from week N-1 or earlier data (verified by audit tests)
  4. Early-season weeks (1-3) produce predictions without crashing despite sparse rolling features
  5. Feature importance report shows top 20 features ranked by contribution to spread/total predictions
**Plans**: 3 plans

Plans:
- [x] 25-01: Game-level differential feature assembly with lag verification
- [x] 25-02: Walk-forward CV framework and XGBoost model training
- [x] 25-03: Training CLI with hyperparameter tuning and feature importance

### Phase 26: Backtesting and Validation
**Goal**: Quantified evidence of model performance against historical Vegas closing lines across multiple seasons
**Depends on**: Phase 25
**Requirements**: BACK-01, BACK-02, BACK-03
**Success Criteria** (what must be TRUE):
  1. Running `python scripts/backtest_predictions.py` produces ATS accuracy, vig-adjusted profit/loss, and ROI for the spread model across training and validation seasons
  2. 2024 season results are computed from a model that never saw 2024 data during training (sealed holdout)
  3. Per-season breakdown shows whether model performance is stable or degrading across validation windows
**Plans**: 2 plans

Plans:
- [x] 26-01: Backtesting framework with ATS accuracy and profit accounting
- [x] 26-02: Holdout validation and stability analysis

### Phase 27: Prediction Pipeline
**Goal**: Users can generate weekly game predictions with edge detection against current Vegas lines
**Depends on**: Phase 26
**Requirements**: PRED-01, PRED-02, PRED-03
**Success Criteria** (what must be TRUE):
  1. Running `python scripts/generate_predictions.py --season 2025 --week 10` produces a table of model spread and total lines for every game that week
  2. Each prediction shows the edge (model line minus Vegas line) with direction and magnitude
  3. Predictions are classified into confidence tiers (high/medium/low edge) so users can filter for strongest plays
  4. Output is saved as Gold-layer Parquet following existing partition conventions (season/week)
**Plans**: 1 plan

Plans:
- [x] 27-01-PLAN.md — TDD: Weekly prediction pipeline with edge detection, confidence tiers, and Gold Parquet output

## Progress

**Execution Order:**
Phases execute in numeric order: 24 -> 25 -> 26 -> 27

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
| 24. Documentation Refresh | v1.4 | 2/2 | Complete    | 2026-03-21 |
| 25. Feature Assembly and Model Training | v1.4 | 3/3 | Complete    | 2026-03-21 |
| 26. Backtesting and Validation | v1.4 | 2/2 | Complete    | 2026-03-21 |
| 27. Prediction Pipeline | v1.4 | 1/1 | Complete   | 2026-03-22 |

---
*Roadmap created: 2026-03-08*
*Last updated: 2026-03-22 after phase 27 planning*
