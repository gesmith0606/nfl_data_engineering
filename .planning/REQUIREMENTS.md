# Requirements: NFL Data Engineering Platform

**Defined:** 2026-03-24
**Core Value:** A rich, well-modeled NFL data lake that serves as the foundation for both fantasy football decision-making and game prediction models.

## v2.0 Requirements

Requirements for Prediction Model Improvement milestone. Each maps to roadmap phases.

### Player Features

- [x] **PLAYER-01**: Compute rolling QB EPA differential (home starter vs away starter) per game
- [x] **PLAYER-02**: Detect starting QB from depth charts with backup flag when starter changes
- [x] **PLAYER-03**: Score team-level injury impact beyond QB (weighted by positional importance)
- [x] **PLAYER-04**: Compute positional quality metrics for RB, WR, and OL aggregated to game level
- [x] **PLAYER-05**: Apply shift(1) lag to all player features to prevent same-week leakage

### Feature Selection

- [x] **FSEL-01**: Remove highly correlated features (r > 0.90) to reduce redundancy
- [x] **FSEL-02**: Compute SHAP importance scores and prune low-signal features
- [x] **FSEL-03**: Run feature selection inside walk-forward CV folds (not on full dataset)
- [x] **FSEL-04**: Enforce holdout season exclusion from all feature selection operations

### Model Ensemble

- [x] **ENS-01**: Train LightGBM base learner with model-specific Optuna search space
- [x] **ENS-02**: Train CatBoost base learner with model-specific tuning constraints
- [x] **ENS-03**: Generate temporal OOF predictions from walk-forward CV for stacking
- [x] **ENS-04**: Train Ridge meta-learner on OOF predictions from all base models
- [x] **ENS-05**: Backtest ensemble model and compare ATS/ROI vs single XGBoost baseline

### Advanced Features

- [x] **ADV-01**: Add momentum/streak signals (win streak, ATS trend) from schedule data
- [x] **ADV-02**: Implement adaptive EWM windows (halflife-based) alongside fixed rolling windows
- [ ] **ADV-03**: Validate marginal improvement of advanced features on holdout

### Infrastructure

- [x] **INFRA-01**: Commit the leakage fix (same-week raw stat exclusion) from feature_engineering.py
- [x] **INFRA-02**: Install LightGBM, CatBoost, and SHAP with Python 3.9 compatible versions

## Future Requirements

Deferred to future milestones. Tracked but not in current roadmap.

### Market Data (v2.3)

- **MKT-01**: Ingest historical odds database (opening/closing lines)
- **MKT-02**: Compute line movement features (steam moves, reverse line movement)
- **MKT-03**: Track closing line value (CLV) for model evaluation

### Betting Framework (v2.4)

- **BET-01**: Kelly criterion position sizing
- **BET-02**: Expected value calculation with vig adjustment
- **BET-03**: Shadow betting tracker with P&L reporting

## Out of Scope

| Feature | Reason |
|---------|--------|
| Neural networks / deep learning | Gradient boosting dominates tabular sports prediction at ~2K game scale |
| Real-time prediction serving | Batch weekly predictions sufficient for current use case |
| Neo4j graph features | Deferred to v3.0+; WR-CB matchup graphs require separate infrastructure |
| Live odds API integration | Market data milestone (v2.3) is a separate scope |
| Player tracking data (Next Gen Stats raw) | Aggregated NGS metrics already in Silver; raw tracking requires different infrastructure |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 28 | Complete |
| INFRA-02 | Phase 28 | Complete |
| PLAYER-01 | Phase 28 | Complete |
| PLAYER-02 | Phase 28 | Complete |
| PLAYER-03 | Phase 28 | Complete |
| PLAYER-04 | Phase 28 | Complete |
| PLAYER-05 | Phase 28 | Complete |
| FSEL-01 | Phase 29 | Complete |
| FSEL-02 | Phase 29 | Complete |
| FSEL-03 | Phase 29 | Complete |
| FSEL-04 | Phase 29 | Complete |
| ENS-01 | Phase 30 | Complete |
| ENS-02 | Phase 30 | Complete |
| ENS-03 | Phase 30 | Complete |
| ENS-04 | Phase 30 | Complete |
| ENS-05 | Phase 30 | Complete |
| ADV-01 | Phase 31 | Complete |
| ADV-02 | Phase 31 | Complete |
| ADV-03 | Phase 31 | Pending |

**Coverage:**
- v2.0 requirements: 19 total
- Mapped to phases: 19
- Unmapped: 0

---
*Requirements defined: 2026-03-24*
*Last updated: 2026-03-24 after roadmap creation (traceability populated)*
