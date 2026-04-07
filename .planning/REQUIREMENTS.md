# Requirements — v3.2 Model Perfection

**Defined:** 2026-04-03
**Core Value:** Push fantasy projection MAE below 4.5 through unified evaluation and advanced modeling

## Unified Evaluation Pipeline

- [x] **EVAL-01**: Training and backtest use identical production heuristic (same multipliers, ceiling shrinkage, injury adjustments)
- [x] **EVAL-02**: Full 466-feature set available during both training and backtest evaluation
- [x] **EVAL-03**: Residual models trained against production heuristic (not simplified version)
- [x] **EVAL-04**: Per-position MAE comparison with full features vs current 42-feature degraded mode

## Full-Feature Residual Deployment

- [ ] **RES-01**: WR residual with full 466 features (current: 42 features, -4.5% improvement; target: -12%+)
- [ ] **RES-02**: TE residual with full 466 features (current: 42 features, -5.0% improvement; target: -10%+)
- [ ] **RES-03**: QB residual evaluated with full features (currently not deployed)
- [ ] **RES-04**: RB residual evaluated with full features (currently not deployed)
- [ ] **RES-05**: Updated ML projection router with best approach per position

## Bayesian Hierarchical Models

- [ ] **BAYES-01**: PyMC or NumPyro dependency added (optional, not required for pipeline)
- [ ] **BAYES-02**: BayesianPlayerModel with position-level priors and player random effects
- [ ] **BAYES-03**: Walk-forward CV evaluation against heuristic and Ridge baselines
- [ ] **BAYES-04**: Posterior predictive intervals for natural floor/ceiling estimation

## Quantile Regression

- [ ] **QUANT-01**: LightGBM quantile mode (10th/50th/90th percentiles) per position per stat
- [ ] **QUANT-02**: Calibration evaluation: 10th < actual < 90th at least 75% of the time
- [ ] **QUANT-03**: Replace hardcoded floor/ceiling with quantile-based bounds in projection_engine.py

## Infrastructure

- [ ] **INFRA-01**: All existing 899+ tests continue passing
- [ ] **INFRA-02**: Overall fantasy MAE below 4.5 (half-PPR, 2022-2024 backtest)
- [ ] **INFRA-03**: No regression for any individual position

## Traceability

| REQ-ID | Phase | Plan | Status |
|--------|-------|------|--------|
| EVAL-01 | 54 | 54-01 | Complete |
| EVAL-02 | 54 | 54-01 | Complete |
| EVAL-03 | 54 | 54-01 | Complete |
| EVAL-04 | 54 | 54-01 | Complete |
| RES-01 | 55 | — | — |
| RES-02 | 55 | — | — |
| RES-03 | 55 | — | — |
| RES-04 | 55 | — | — |
| RES-05 | 55 | — | — |
| BAYES-01 | 56 | — | — |
| BAYES-02 | 56 | — | — |
| BAYES-03 | 56 | — | — |
| BAYES-04 | 56 | — | — |
| QUANT-01 | 57 | — | — |
| QUANT-02 | 57 | — | — |
| QUANT-03 | 57 | — | — |
| INFRA-01 | all | — | — |
| INFRA-02 | all | — | — |
| INFRA-03 | all | — | — |

## Future Requirements (deferred)
- PFF data integration (v3.3)
- Neural embeddings (rejected — insufficient data)
- DST fantasy projections

## Out of Scope
- Website deployment (tracked in v4.0 parallel milestone)
- Sleeper integration (v4.0)
- Game prediction model improvements (separate track)
