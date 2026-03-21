# Requirements: NFL Data Engineering Platform

**Defined:** 2026-03-20
**Core Value:** A rich NFL data lake powering both fantasy football projections and game prediction models

## v1.4 Requirements

Requirements for ML Game Prediction milestone. Each maps to roadmap phases.

### Documentation

- [x] **DOCS-01**: Data dictionary updated with all 11 Silver layer table schemas and column definitions
- [x] **DOCS-02**: Data dictionary updated with Gold layer prediction output schemas
- [x] **DOCS-03**: CLAUDE.md refreshed with current architecture, key files, test counts, and status
- [x] **DOCS-04**: Implementation guide updated with v1.3 phases and current prediction model status badges
- [x] **DOCS-05**: Bronze inventory regenerated showing PBP 140 columns and officials data type

### Feature Engineering

- [x] **FEAT-01**: Game-level differential features computed (home_metric - away_metric) from Silver team data
- [x] **FEAT-02**: All Silver sources audited and verified to use only week N-1 data for week N predictions
- [x] **FEAT-03**: Feature importance analysis using XGBoost built-in importance and/or SHAP values
- [x] **FEAT-04**: Early-season (Weeks 1-3) NaN handling strategy implemented for sparse rolling features

### Model Training

- [x] **MODL-01**: XGBoost spread prediction model trained on differential features with walk-forward CV
- [x] **MODL-02**: XGBoost over/under prediction model trained on differential features with walk-forward CV
- [x] **MODL-03**: Walk-forward cross-validation framework (train seasons 1..N, validate N+1)
- [x] **MODL-04**: Optuna hyperparameter tuning for tree depth, learning rate, and regularization
- [x] **MODL-05**: Conservative default hyperparameters (shallow trees, strong regularization, early stopping)

### Backtesting

- [ ] **BACK-01**: ATS accuracy computed against historical closing lines with vig-adjusted profit/loss
- [ ] **BACK-02**: 2024 season sealed as untouched holdout for final model validation
- [ ] **BACK-03**: Per-season stability analysis across training and validation windows

### Prediction Pipeline

- [ ] **PRED-01**: Weekly prediction pipeline generating model spread and total lines for upcoming games
- [ ] **PRED-02**: Edge detection comparing model lines vs Vegas closing lines per game
- [ ] **PRED-03**: Confidence scoring with tiers (high/medium/low edge) per game prediction

## Future Requirements

Deferred to future milestones. Tracked but not in current roadmap.

### Fantasy ML Upgrade

- **FANT-01**: Replace weighted-average fantasy projections with ML model
- **FANT-02**: Position-specific ML models for QB/RB/WR/TE projections

### Sleeper Integration

- **SLPR-01**: Live Sleeper league sync for roster/waiver decisions
- **SLPR-02**: Automated waiver wire recommendations based on projections

## Out of Scope

| Feature | Reason |
|---------|--------|
| Neural networks / deep learning | Gradient boosting dominates tabular sports prediction; ~1,900 games too small for NN |
| Real-time prediction serving | Batch weekly predictions sufficient; no live inference needed |
| Neo4j graph features | Deferred until prediction model validated |
| Vegas lines as input features | Research explicitly flags this — zero edge by definition |
| LightGBM as primary model | XGBoost sufficient; LightGBM adds complexity without clear benefit at this scale |
| S3 sync | AWS credentials expired; local-first workflow |
| Player-level game prediction features | Team-level differentials sufficient for game outcomes |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DOCS-01 | Phase 24 | Complete |
| DOCS-02 | Phase 24 | Complete |
| DOCS-03 | Phase 24 | Complete |
| DOCS-04 | Phase 24 | Complete |
| DOCS-05 | Phase 24 | Complete |
| FEAT-01 | Phase 25 | Complete |
| FEAT-02 | Phase 25 | Complete |
| FEAT-03 | Phase 25 | Complete |
| FEAT-04 | Phase 25 | Complete |
| MODL-01 | Phase 25 | Complete |
| MODL-02 | Phase 25 | Complete |
| MODL-03 | Phase 25 | Complete |
| MODL-04 | Phase 25 | Complete |
| MODL-05 | Phase 25 | Complete |
| BACK-01 | Phase 26 | Pending |
| BACK-02 | Phase 26 | Pending |
| BACK-03 | Phase 26 | Pending |
| PRED-01 | Phase 27 | Pending |
| PRED-02 | Phase 27 | Pending |
| PRED-03 | Phase 27 | Pending |

**Coverage:**
- v1.4 requirements: 20 total
- Mapped to phases: 20
- Unmapped: 0

---
*Requirements defined: 2026-03-20*
*Last updated: 2026-03-20 after roadmap creation*
