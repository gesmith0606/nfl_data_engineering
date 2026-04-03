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
- v3.0 Player Fantasy Prediction System -- Phases 39-48 (shipped 2026-04-01)
- v3.1 Graph-Enhanced Fantasy Projections -- Phases 49-53 (shipped 2026-04-03)
- **v3.2 Model Perfection -- Phases 54-57 (current)**
- *v4.0 Production Launch -- Phases W7-W12 (parallel, see .planning/v4.0-web/)*

---

## v3.2 Model Perfection

**Goal:** Push fantasy MAE below 4.5 through unified evaluation pipeline and advanced modeling.

**Current baseline:** MAE 4.77 (QB 6.58, RB 5.00, WR 4.63, TE 3.58)

### Phase 54: Unified Evaluation Pipeline
**Goal:** Align training and backtest to use the same production heuristic and full 466-feature set.
**Requirements:** EVAL-01, EVAL-02, EVAL-03, EVAL-04
**Dependencies:** None
**Success criteria:**
1. Backtest generates production heuristic projections with ALL multipliers (usage, matchup, Vegas, ceiling shrinkage)
2. Full 466-feature set assembled and available during backtest evaluation
3. Residual models retrained against production heuristic (not simplified)
4. Per-position MAE comparison: degraded (42 features) vs full (466 features)
5. Tests passing

### Phase 55: Full-Feature Residual Deployment
**Goal:** Deploy residual models with full features for all positions, update router.
**Requirements:** RES-01, RES-02, RES-03, RES-04, RES-05
**Dependencies:** Phase 54 (unified pipeline must exist)
**Success criteria:**
1. WR residual improvement increases from -4.5% to -10%+ with full features
2. TE residual improvement increases from -5.0% to -8%+ with full features
3. QB and RB residual evaluated — ship if beats standalone
4. ML projection router updated with best approach per position
5. Overall MAE improved (target: < 4.5)

### Phase 56: Bayesian Hierarchical Models
**Goal:** Implement Bayesian player models with partial pooling and posterior uncertainty.
**Requirements:** BAYES-01, BAYES-02, BAYES-03, BAYES-04
**Dependencies:** Phase 54 (needs unified evaluation for fair comparison)
**Success criteria:**
1. PyMC or NumPyro model implemented with position-level priors
2. Walk-forward CV completed with same folds as Ridge/XGB
3. MAE compared to heuristic, Ridge, and XGB per position
4. Posterior predictive intervals provide calibrated floor/ceiling
5. Ship if any position improves; valuable even if MAE is similar (uncertainty)

### Phase 57: Quantile Regression + Final Validation
**Goal:** Replace hardcoded floor/ceiling with data-driven percentiles, run final validation.
**Requirements:** QUANT-01, QUANT-02, QUANT-03, INFRA-01, INFRA-02, INFRA-03
**Dependencies:** Phases 55-56 (final model state must be known)
**Success criteria:**
1. LightGBM quantile models trained for 10th/50th/90th percentiles
2. Calibration: 80% of actuals fall within 10th-90th range
3. Floor/ceiling in projection_engine.py uses quantile bounds
4. Final backtest: overall MAE < 4.5
5. All tests passing, docs updated

---

## Requirement Coverage

| REQ-ID | Phase | Description |
|--------|-------|-------------|
| EVAL-01 | 54 | Identical production heuristic |
| EVAL-02 | 54 | Full 466-feature set |
| EVAL-03 | 54 | Residual trained vs production |
| EVAL-04 | 54 | Per-position MAE comparison |
| RES-01 | 55 | WR full-feature residual |
| RES-02 | 55 | TE full-feature residual |
| RES-03 | 55 | QB residual evaluation |
| RES-04 | 55 | RB residual evaluation |
| RES-05 | 55 | Router update |
| BAYES-01 | 56 | PyMC/NumPyro dependency |
| BAYES-02 | 56 | Bayesian model implementation |
| BAYES-03 | 56 | Walk-forward CV evaluation |
| BAYES-04 | 56 | Posterior predictive intervals |
| QUANT-01 | 57 | Quantile regression models |
| QUANT-02 | 57 | Calibration evaluation |
| QUANT-03 | 57 | Replace hardcoded floor/ceiling |
| INFRA-01 | all | Tests passing |
| INFRA-02 | all | MAE < 4.5 |
| INFRA-03 | all | No position regression |

**Coverage: 19/19 requirements mapped (100%)**
