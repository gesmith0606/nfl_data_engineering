# Requirements: NFL Data Engineering Platform

**Defined:** 2026-03-15
**Core Value:** A rich, well-modeled NFL data lake that serves as the foundation for both fantasy football decision-making and game prediction models

## v1.3 Requirements

Requirements for v1.3 Prediction Data Foundation. Each maps to roadmap phases.

### Infrastructure

- [ ] **INFRA-01**: PBP column expansion (~25 columns for penalties, special teams, fumbles, drives) with re-ingestion of historical PBP data
- [ ] **INFRA-02**: Officials Bronze ingestion via `import_officials()` with historical coverage (2016-2025)
- [ ] **INFRA-03**: Stadium coordinates CSV (~35 venues) for travel distance computation

### PBP-Derived Metrics

- [ ] **PBP-01**: Team penalty rates (count, yards/game, offensive holding/DPI/roughing) with off/def split and rolling windows
- [ ] **PBP-02**: Opponent-drawn penalty rates with rolling windows
- [ ] **PBP-03**: Turnover luck metrics (fumble recovery rate, earned vs lucky turnovers, regression-to-mean indicator)
- [ ] **PBP-04**: Red zone trip volume (drive-level counts per team/game, not just efficiency rates)
- [ ] **PBP-05**: Special teams FG accuracy by distance bucket (short/mid/long) with rolling windows
- [ ] **PBP-06**: Special teams punt/kick return averages and touchback rates with rolling windows
- [ ] **PBP-07**: 3rd down conversion rates (off/def) with rolling windows
- [ ] **PBP-08**: Explosive play rates (20+ yd pass, 10+ yd rush) off/def with rolling windows
- [ ] **PBP-09**: Drive efficiency (3-and-out rate, avg drive length in plays and yards, drives/game) with rolling windows
- [ ] **PBP-10**: Team sack rates (OL protection rate + defensive pass rush rate) with rolling windows
- [ ] **PBP-11**: Time of possession per team with rolling windows

### Schedule-Derived Features

- [ ] **SCHED-01**: Weather features (temperature, wind speed, roof type, surface type) from schedules Bronze as Silver columns
- [ ] **SCHED-02**: Rest days (days since last game, bye week timing, short week flag) per team/week
- [ ] **SCHED-03**: Travel distance between venues using stadium coordinates lookup
- [ ] **SCHED-04**: Time zone differential for cross-country games
- [ ] **SCHED-05**: Head coach per game with coaching change detection flag (mid-season and off-season)

### Cross-Source Features

- [ ] **CROSS-01**: Referee tendency profiles (penalty rate, scoring impact per crew) joining schedules referee with penalty Silver metrics
- [ ] **CROSS-02**: Playoff/elimination context (win/loss standings, division rank, clinch/elimination flag) using simple proxy method

### Integration

- [ ] **INTEG-01**: Pipeline health monitoring for all new Silver output paths
- [ ] **INTEG-02**: All new features use rolling windows (3-game, 6-game, season-to-date) with shift(1) lag to prevent look-ahead bias

## Future Requirements

Deferred to future milestones. Tracked but not in current roadmap.

### Coaching Expansion

- **COACH-01**: OC/DC coordinator tracking per game (requires manual CSV curation — no automated source)
- **COACH-02**: Scheme classification (West Coast, Air Raid, zone run, etc.) per coaching staff

### Advanced Weather

- **WTHR-01**: Precipitation and humidity data from external weather API (meteostat)
- **WTHR-02**: Weather impact scoring model (combine temp + wind + precip into single adjustment factor)

### ML Model Build

- **ML-01**: Game outcome prediction model (spread, total, moneyline) using Gold feature vectors
- **ML-02**: Fantasy projection upgrade (XGBoost/LightGBM replacing weighted averages)

## Out of Scope

| Feature | Reason |
|---------|--------|
| OC/DC coordinator data | No automated source; requires manual curation — defer to future milestone |
| Full NFL tiebreaker logic | Multi-week effort for near-zero signal before Week 14; simple standings proxy captures 95% of value |
| External weather API | Schedules already has temp/wind/roof/surface; defer until backtesting proves value |
| Neo4j graph layer | Phase 5 from original project; deferred until prediction model validated |
| Live betting / in-game prediction | Requires real-time data pipeline; fundamentally different architecture |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 20 | Pending |
| INFRA-02 | Phase 20 | Pending |
| INFRA-03 | Phase 20 | Pending |
| PBP-01 | Phase 21 | Pending |
| PBP-02 | Phase 21 | Pending |
| PBP-03 | Phase 21 | Pending |
| PBP-04 | Phase 21 | Pending |
| PBP-05 | Phase 21 | Pending |
| PBP-06 | Phase 21 | Pending |
| PBP-07 | Phase 21 | Pending |
| PBP-08 | Phase 21 | Pending |
| PBP-09 | Phase 21 | Pending |
| PBP-10 | Phase 21 | Pending |
| PBP-11 | Phase 21 | Pending |
| INTEG-02 | Phase 21 | Pending |
| SCHED-01 | Phase 22 | Pending |
| SCHED-02 | Phase 22 | Pending |
| SCHED-03 | Phase 22 | Pending |
| SCHED-04 | Phase 22 | Pending |
| SCHED-05 | Phase 22 | Pending |
| CROSS-01 | Phase 23 | Pending |
| CROSS-02 | Phase 23 | Pending |
| INTEG-01 | Phase 23 | Pending |

**Coverage:**
- v1.3 requirements: 23 total
- Mapped to phases: 23
- Unmapped: 0

---
*Requirements defined: 2026-03-15*
*Last updated: 2026-03-15 after roadmap creation — all 23 requirements mapped*
