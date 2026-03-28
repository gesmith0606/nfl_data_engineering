# Requirements: NFL Data Engineering Platform

**Defined:** 2026-03-28
**Core Value:** A rich, well-modeled NFL data lake that serves as the foundation for both fantasy football decision-making and game prediction models

## v2.2 Requirements

Requirements for v2.2 Full Odds + Holdout Reset. Each maps to roadmap phases.

### Bronze Data Expansion

- [ ] **BRNZ-01**: Full FinnedAI odds ingested for all 6 seasons (2016-2021) with cross-validation passing r > 0.95 per season
- [ ] **BRNZ-02**: nflverse schedule odds extracted for 2022-2025 with closing spread_line and total_line stored as Bronze Parquet
- [ ] **BRNZ-03**: 2025 season fully ingested across all Bronze data types (schedules, PBP, player_weekly, player_seasonal, snap_counts, injuries, rosters, teams)

### Silver + Feature Vector

- [ ] **SLVR-01**: Silver market data generated for all FinnedAI seasons (2016-2021) with line movement features
- [ ] **SLVR-02**: All Silver transformations run for 2025 (player usage, team metrics, game context, advanced profiles, player quality)
- [ ] **SLVR-03**: Full prediction feature vector assembled for 2025 games with market features populated where available

### Holdout + Model

- [ ] **HOLD-01**: Holdout season rotated from 2024 to 2025 in config.py with all holdout guards updated
- [ ] **HOLD-02**: TRAINING/VALIDATION/PREDICTION_SEASONS computed automatically from HOLDOUT_SEASON
- [ ] **HOLD-03**: Ensemble retrained on 2016-2024 with sealed 2025 baseline (ATS accuracy, profit, CLV documented)
- [ ] **HOLD-04**: Market feature ablation re-run on 2025 holdout with 6 seasons of training market data and ship-or-skip verdict

## Future Requirements

Deferred to future milestones. Tracked but not in current roadmap.

### Player Prediction (v3.0)

- **PRED-01**: Opportunity models (snap share, target share, carry share, red zone share)
- **PRED-02**: Efficiency models (yards per target, TD rate, catch rate)
- **PRED-03**: Matchup context (defense vs position, game script, pace projection)
- **PRED-04**: Game-level constraints (coherent team-level allocation)
- **PRED-05**: Regime detection (coaching changes, injuries, role shifts)
- **PRED-06**: Per-stat evaluation framework (MAE per stat, calibration, vs Vegas props)

### Production + Delivery (v4.0+)

- **PROD-01**: Automated weekly pipeline with drift detection
- **PROD-02**: Web MVP with projections and lines display
- **PROD-03**: Fantasy agent with LLM-powered recommendations

## Out of Scope

| Feature | Reason |
|---------|--------|
| Paid odds API (The Odds API, SportsDataIO) | Recurring cost ($50-500/mo); nflverse closing lines sufficient for batch prediction |
| FinnedAI scraper re-run for 2022+ | Scraper unmaintained since Dec 2023; CLI date range capped at 2021 |
| Opening line features for 2022+ | No free source available; gradient boosting handles NaN natively |
| Multiple sportsbook line comparison | Schema complexity for unclear model lift; single consensus line sufficient |
| AusSportsBetting.com integration | Same closing-line data as nflverse; more complex schema; personal-use license |
| Automatic holdout rotation schedule | Premature unsealing wastes holdout integrity; manual rotation at milestone boundaries |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| BRNZ-01 | — | Pending |
| BRNZ-02 | — | Pending |
| BRNZ-03 | — | Pending |
| SLVR-01 | — | Pending |
| SLVR-02 | — | Pending |
| SLVR-03 | — | Pending |
| HOLD-01 | — | Pending |
| HOLD-02 | — | Pending |
| HOLD-03 | — | Pending |
| HOLD-04 | — | Pending |

**Coverage:**
- v2.2 requirements: 10 total
- Mapped to phases: 0
- Unmapped: 10 ⚠️

---
*Requirements defined: 2026-03-28*
*Last updated: 2026-03-28 after initial definition*
