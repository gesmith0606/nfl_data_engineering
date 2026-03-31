# Requirements: NFL Data Engineering Platform

**Defined:** 2026-03-29
**Core Value:** A rich, well-modeled NFL data lake that serves as the foundation for both fantasy football decision-making and game prediction models

## v3.0 Requirements

Requirements for ML-based player fantasy prediction system. Each maps to roadmap phases.

### Feature Assembly

- [x] **FEAT-01**: Player-level feature vector assembled from 9 Silver sources into per-player-per-week rows with proper temporal lags
- [x] **FEAT-02**: All player features use shift(1) to prevent same-game stat leakage
- [x] **FEAT-03**: Matchup features include opponent defense vs position rank and EPA allowed, lagged to week N-1
- [x] **FEAT-04**: Vegas implied team totals derived from spread/total lines included as features

### Model Training

- [x] **MODL-01**: Separate gradient boosting models trained per position (QB, RB, WR, TE)
- [x] **MODL-02**: Walk-forward temporal CV respecting season/week ordering with 2025 holdout sealed
- [x] **MODL-03**: Per-position MAE/RMSE/correlation evaluation against heuristic baseline (QB:6.58, RB:5.06, WR:4.85, TE:3.77)
- [x] **MODL-04**: Ship-or-skip gate requiring 4%+ per-position MAE improvement over heuristic to replace it

### Accuracy

- [ ] **ACCY-01**: Opportunity-efficiency decomposition predicting shares/volume then per-touch efficiency
- [ ] **ACCY-02**: TD regression features using red zone opportunity share x historical conversion rates
- [ ] **ACCY-03**: Role momentum features (snap share trajectory as breakout/demotion signal)
- [ ] **ACCY-04**: Ensemble stacking (XGB+LGB+CB+Ridge) per position if single model leaves accuracy on the table

### Pipeline & Integration

- [x] **PIPE-01**: Stat-level predictions (yards, TDs, receptions) with scoring formula applied downstream
- [ ] **PIPE-02**: Team-total constraint ensuring player share projections sum to ~100% per team
- [ ] **PIPE-03**: Weekly pipeline wiring into generate_projections.py and draft_assistant.py
- [ ] **PIPE-04**: Heuristic fallback preserved for rookies, thin-data players, and positions where ML doesn't beat baseline

### Extensions

- [ ] **EXTD-01**: Preseason projection mode using prior-season aggregates + draft capital when no current-season data exists
- [ ] **EXTD-02**: ML-derived confidence intervals (MAPIE) for player-specific floor/ceiling bands

## Future Requirements

### Graph-Enhanced Predictions (v3.1)

- **GRPH-01**: Neo4j graph database with player relationship edges
- **GRPH-02**: WR-CB matchup features from snap-level alignment data
- **GRPH-03**: Target network features (QB-WR connection strength)
- **GRPH-04**: Graph features integrated into both game and player prediction models

### Production Pipeline (v4.0)

- **PROD-01**: Automated weekly pipeline with drift detection
- **PROD-02**: Model monitoring and retraining triggers
- **PROD-03**: FastAPI backend for serving predictions

## Out of Scope

| Feature | Reason |
|---------|--------|
| Deep learning / LSTM models | Gradient boosting dominates tabular NFL data at this scale (~50K player-weeks); adds PyTorch/GPU complexity |
| WR-CB snap-level matchups | Requires Neo4j + snap-level data pipeline; deferred to v3.1 |
| Real-time in-game projections | Requires streaming infrastructure; weekly batch serves 99% of fantasy use cases |
| Injury prediction model | Injury occurrence is essentially random; focus on injury *impact* not prediction |
| Weather as direct feature | Small effect (~2-5%) already captured by Vegas lines; adds noise at player level |
| Multi-book line comparison | Single consensus line sufficient; v4.0+ concern |
| Dynasty / multi-year projections | Different problem than weekly projections; separate future milestone |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| FEAT-01 | Phase 39 | Complete |
| FEAT-02 | Phase 39 | Complete |
| FEAT-03 | Phase 39 | Complete |
| FEAT-04 | Phase 39 | Complete |
| MODL-01 | Phase 40 | Complete |
| MODL-02 | Phase 40 | Complete |
| MODL-03 | Phase 40 | Complete |
| MODL-04 | Phase 40 | Complete |
| ACCY-01 | Phase 41 | Pending |
| ACCY-02 | Phase 41 | Pending |
| ACCY-03 | Phase 41 | Pending |
| ACCY-04 | Phase 41 | Pending |
| PIPE-01 | Phase 40 | Complete |
| PIPE-02 | Phase 42 | Pending |
| PIPE-03 | Phase 42 | Pending |
| PIPE-04 | Phase 42 | Pending |
| EXTD-01 | Phase 42 | Pending |
| EXTD-02 | Phase 42 | Pending |

**Coverage:**
- v3.0 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0

---
*Requirements defined: 2026-03-29*
*Last updated: 2026-03-29 after roadmap phase mapping*
