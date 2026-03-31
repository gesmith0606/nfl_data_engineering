# Roadmap: NFL Data Engineering Platform

## Milestones

- v1.0 Bronze Expansion -- Phases 1-7 (shipped 2026-03-08)
- v1.1 Bronze Backfill -- Phases 8-14 (shipped 2026-03-13)
- v1.2 Silver Expansion -- Phases 15-19 (shipped 2026-03-15)
- v1.3 Prediction Data Foundation -- Phases 20-23 (shipped 2026-03-19)
- v1.4 ML Game Prediction -- Phases 24-27 (shipped 2026-03-22)
- v2.0 Prediction Model Improvement -- Phases 28-31 (shipped 2026-03-27)
- v2.1 Market Data -- Phases 32-34 (shipped 2026-03-28)
- v2.2 Full Odds + Holdout Reset -- Phases 35-38 (shipped 2026-03-29)
- v3.0 Player Fantasy Prediction System -- Phases 39-42 (in progress)

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

<details>
<summary>v2.2 Full Odds + Holdout Reset (Phases 35-38) -- SHIPPED 2026-03-29</summary>

- [x] Phase 35: Bronze Data Completion (2/2 plans) -- completed 2026-03-28
- [x] Phase 36: Silver and Feature Vector Assembly (2/2 plans) -- completed 2026-03-29
- [x] Phase 37: Holdout Reset and Baseline (2/2 plans) -- completed 2026-03-29
- [x] Phase 38: Market Feature Ablation (1/1 plan) -- completed 2026-03-29

Full details: `.planning/milestones/v2.2-ROADMAP.md`

</details>

### v3.0 Player Fantasy Prediction System (In Progress)

**Milestone Goal:** Replace heuristic player projections with ML-based per-position models that predict raw stats and derive fantasy points via the existing scoring calculator. The build progresses from feature assembly (highest leakage risk) through baseline models with a ship-or-skip gate, optional accuracy improvements, and pipeline integration.

- [x] **Phase 39: Player Feature Vector Assembly** - Build player-week feature vectors from Silver sources with temporal lag enforcement and leakage prevention (completed 2026-03-30)
- [ ] **Phase 40: Baseline Models and Ship Gate** - Train per-position gradient boosting models with walk-forward CV; evaluate against heuristic baselines; ship-or-skip decision
- [ ] **Phase 41: Accuracy Improvements** - Opportunity-efficiency decomposition, TD regression, role momentum, and ensemble stacking to push per-position MAE further
- [ ] **Phase 42: Pipeline Integration and Extensions** - Wire ML predictions into weekly pipeline, draft tool, and projection CLI; add team constraints, preseason mode, and confidence intervals

## Phase Details

### Phase 39: Player Feature Vector Assembly
**Goal**: Users can generate a validated player-week feature matrix from existing Silver data with guaranteed temporal integrity
**Depends on**: Nothing (first phase of v3.0; builds on existing Silver layer from v2.2)
**Requirements**: FEAT-01, FEAT-02, FEAT-03, FEAT-04
**Success Criteria** (what must be TRUE):
  1. Running the player feature assembler produces a per-player-per-week DataFrame joining usage, advanced, historical, opponent, team context, player quality, and market data from Silver
  2. Every feature column passes a temporal integrity check confirming shift(1) lag -- no same-game stats leak into features
  3. Matchup features include opponent defense-vs-position rank and EPA allowed, lagged to week N-1, for all four positions
  4. Vegas implied team totals (derived from spread and total lines) appear as features in the player-week rows
  5. A leakage detection validator flags any feature with r > 0.90 correlation to the target variable
**Plans**: 2 plans

Plans:
- [x] 39-01-PLAN.md — Core player feature assembly module, config, and unit tests
- [x] 39-02-PLAN.md — CLI script and integration tests on real data

### Phase 40: Baseline Models and Ship Gate
**Goal**: Per-position ML models produce stat-level predictions that are objectively measured against the heuristic baseline, with a clear ship-or-skip verdict
**Depends on**: Phase 39
**Requirements**: MODL-01, MODL-02, MODL-03, MODL-04, PIPE-01
**Success Criteria** (what must be TRUE):
  1. Separate gradient boosting models exist for QB, RB, WR, and TE, each predicting raw stat components (yards, TDs, receptions) rather than fantasy points directly
  2. All models are trained using walk-forward temporal CV respecting season/week ordering with 2025 holdout sealed and never touched during training
  3. Per-position MAE, RMSE, and correlation are reported independently and compared side-by-side against heuristic baselines (QB: 6.58, RB: 5.06, WR: 4.85, TE: 3.77)
  4. A ship-or-skip gate produces a clear verdict: positions where ML achieves 4%+ MAE improvement over heuristic are shipped; others fall back to heuristic
**Plans**: 2 plans

Plans:
- [x] 40-01-PLAN.md — Core player model training module with walk-forward CV, feature selection, and model serialization
- [ ] 40-02-PLAN.md — Ship gate evaluation CLI with heuristic comparison and SHIP/SKIP verdict

### Phase 41: Accuracy Improvements
**Goal**: Per-position prediction accuracy improves beyond the baseline models through decomposition, regression features, and ensemble stacking
**Depends on**: Phase 40 (only executed if ship gate identifies room for improvement)
**Requirements**: ACCY-01, ACCY-02, ACCY-03, ACCY-04
**Success Criteria** (what must be TRUE):
  1. Opportunity-efficiency decomposition predicts volume (targets, carries, snap share) separately from per-touch efficiency (yards/target, TD rate, catch rate), then combines them into stat predictions
  2. TD regression features use red zone opportunity share multiplied by historical conversion rates instead of raw TD rolling averages
  3. Role momentum features (snap share trajectory as breakout/demotion signal) are available as model inputs
  4. Ensemble stacking (XGB+LGB+CB+Ridge) is applied per position where a single model leaves measurable accuracy on the table
**Plans**: TBD

Plans:
- [ ] 41-01: TBD
- [ ] 41-02: TBD

### Phase 42: Pipeline Integration and Extensions
**Goal**: ML predictions are wired into the weekly pipeline, draft tool, and projection CLI with team coherence, preseason mode, and confidence intervals
**Depends on**: Phase 40 (minimum); Phase 41 (if executed)
**Requirements**: PIPE-02, PIPE-03, PIPE-04, EXTD-01, EXTD-02
**Success Criteria** (what must be TRUE):
  1. Player share projections within a team sum to approximately 100% per stat category, enforced by team-total constraints derived from game prediction implied totals
  2. Running `generate_projections.py` with `--ml` flag produces ML-based projections; the draft assistant and weekly pipeline consume them seamlessly
  3. Rookies, thin-data players, and positions where ML did not beat the heuristic automatically fall back to the heuristic projection engine
  4. Preseason projection mode uses prior-season aggregates plus draft capital when no current-season data exists
  5. ML-derived confidence intervals (MAPIE) provide player-specific floor/ceiling bands replacing the heuristic shrinkage approach

**Plans**: TBD

Plans:
- [ ] 42-01: TBD
- [ ] 42-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 39 -> 40 -> 41 (conditional on ship gate) -> 42

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1-7 | v1.0 | 11/11 | Complete | 2026-03-08 |
| 8-14 | v1.1 | 12/12 | Complete | 2026-03-13 |
| 15-19 | v1.2 | 10/10 | Complete | 2026-03-15 |
| 20-23 | v1.3 | 9/9 | Complete | 2026-03-19 |
| 24-27 | v1.4 | 8/8 | Complete | 2026-03-22 |
| 28-31 | v2.0 | 8/8 | Complete | 2026-03-27 |
| 32-34 | v2.1 | 6/6 | Complete | 2026-03-28 |
| 35-38 | v2.2 | 7/7 | Complete | 2026-03-29 |
| 39 | v3.0 | 2/2 | Complete    | 2026-03-30 |
| 40 | v3.0 | 1/2 | In Progress|  |
| 41 | v3.0 | 0/TBD | Not started | - |
| 42 | v3.0 | 0/TBD | Not started | - |

---
*Roadmap created: 2026-03-08*
*Last updated: 2026-03-30 after phase 40 planning*
