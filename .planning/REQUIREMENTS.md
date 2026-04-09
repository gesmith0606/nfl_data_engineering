# Requirements — v3.2 Model Perfection

**Defined:** 2026-04-03
**Core Value:** Push fantasy projection MAE below 4.5 through unified evaluation and advanced modeling

## Unified Evaluation Pipeline

- [x] **EVAL-01**: Training and backtest use identical production heuristic (same multipliers, ceiling shrinkage, injury adjustments)
- [x] **EVAL-02**: Full 466-feature set available during both training and backtest evaluation
- [x] **EVAL-03**: Residual models trained against production heuristic (not simplified version)
- [x] **EVAL-04**: Per-position MAE comparison with full features vs current 42-feature degraded mode

## Full-Feature Residual Deployment

- [x] **RES-01**: WR residual with LGB + SHAP-60 features (-31.4% MAE improvement in walk-forward CV)
- [x] **RES-02**: TE residual with LGB + SHAP-60 features (-27.2% MAE improvement in walk-forward CV)
- [x] **RES-03**: QB residual evaluated (-72.2% improvement); LGB deployed for all positions
- [x] **RES-04**: RB residual evaluated (-25.1% improvement); LGB deployed for all positions
- [x] **RES-05**: Updated ML projection router: QB/RB XGBoost SHIP, WR/TE HYBRID (heuristic + LGB residual)

## Bayesian Hierarchical Models

- [x] **BAYES-01**: PyMC or NumPyro dependency added (optional, not required for pipeline)
- [x] **BAYES-02**: BayesianPlayerModel with position-level priors and player random effects
- [x] **BAYES-03**: Walk-forward CV evaluation against heuristic and Ridge baselines
- [x] **BAYES-04**: Posterior predictive intervals for natural floor/ceiling estimation

## Quantile Regression

- [x] **QUANT-01**: LightGBM quantile mode (10th/50th/90th percentiles) — 12 models trained
- [x] **QUANT-02**: Calibration evaluation: 74.8-81.8% coverage (QB slightly under, WR/TE meet 80%)
- [x] **QUANT-03**: Replace hardcoded floor/ceiling with quantile-based bounds in projection_engine.py

## Infrastructure

- [x] **INFRA-01**: 1,319 tests passing (up from 899 baseline)
- [ ] **INFRA-02**: Overall fantasy MAE 4.80 — target 4.5 NOT MET (see EXPERIMENTS.md)
- [x] **INFRA-03**: No position regression from quantile addition; QB improved 6.72->6.58; TE minor +0.12

## Traceability

| REQ-ID | Phase | Plan | Status |
|--------|-------|------|--------|
| EVAL-01 | 54 | 54-01 | Complete |
| EVAL-02 | 54 | 54-01 | Complete |
| EVAL-03 | 54 | 54-01 | Complete |
| EVAL-04 | 54 | 54-01 | Complete |
| RES-01 | 55 | 55-01 | Complete |
| RES-02 | 55 | 55-01 | Complete |
| RES-03 | 55 | 55-01 | Complete |
| RES-04 | 55 | 55-01 | Complete |
| RES-05 | 55 | 55-01 | Complete |
| BAYES-01 | 56 | 56-01 | Complete |
| BAYES-02 | 56 | 56-01 | Complete |
| BAYES-03 | 56 | 56-01 | Complete |
| BAYES-04 | 56 | 56-01 | Complete |
| QUANT-01 | 57 | 57-01 | Complete |
| QUANT-02 | 57 | 57-01 | Complete |
| QUANT-03 | 57 | 57-01 | Complete |
| INFRA-01 | all | 57-01 | Complete |
| INFRA-02 | all | 57-01 | NOT MET (4.80 > 4.5) |
| INFRA-03 | all | 57-01 | Complete |

## Future Requirements (deferred)
- PFF data integration (v3.3)
- Neural embeddings (rejected — insufficient data)
- DST fantasy projections

## Out of Scope
- Website deployment (tracked in v4.0 parallel milestone)
- Sleeper integration (v4.0)
- Game prediction model improvements (separate track)
