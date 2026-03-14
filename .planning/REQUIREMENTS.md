# Requirements: NFL Data Engineering — Silver Expansion

**Defined:** 2026-03-13
**Core Value:** A rich, well-modeled NFL data lake that serves as the foundation for both fantasy football decision-making and game prediction models.

## v1.2 Requirements

Requirements for Silver layer expansion. Each maps to roadmap phases.

### PBP Team Metrics

- [x] **PBP-01**: Team EPA per play (offense + defense, pass/rush splits) computed from Bronze PBP with 3-game and 6-game rolling windows
- [x] **PBP-02**: Team success rate (offense + defense) with rolling windows
- [x] **PBP-03**: Team CPOE aggregate (per QB and per team) with rolling windows
- [x] **PBP-04**: Red zone efficiency (offense + defense — TD rate, success rate, pass/rush split inside 20) with rolling windows
- [x] **PBP-05**: Existing rolling window bug fixed — groupby must use (entity, season) not entity alone

### Team Tendencies

- [ ] **TEND-01**: Pace (plays per game) per team with rolling windows
- [ ] **TEND-02**: Pass Rate Over Expected (PROE) per team with rolling windows
- [ ] **TEND-03**: 4th down aggressiveness index (go rate, success rate) with rolling windows
- [ ] **TEND-04**: Early-down run rate with rolling windows

### Situational Breakdowns

- [ ] **SIT-01**: Home/away performance splits with rolling windows
- [ ] **SIT-02**: Divisional vs non-divisional game tags and performance splits
- [ ] **SIT-03**: Game script splits (leading/trailing by 7+) with rolling EPA

### Strength of Schedule

- [ ] **SOS-01**: Opponent-adjusted EPA using lagged opponent strength (through week N-1 only)
- [ ] **SOS-02**: Schedule difficulty rankings (1-32) per team per week

### Advanced Player Profiles

- [ ] **PROF-01**: NGS WR/TE profile (separation, catch probability, intended air yards) with rolling windows
- [ ] **PROF-02**: NGS QB profile (time-to-throw, aggressiveness, completed air yards) with rolling windows
- [ ] **PROF-03**: NGS RB profile (rush yards over expected, efficiency) with rolling windows
- [ ] **PROF-04**: PFR pressure rate (hits + hurries + sacks / dropbacks) per QB with rolling windows
- [ ] **PROF-05**: PFR blitz rate per defensive team with rolling windows
- [ ] **PROF-06**: QBR rolling windows (total QBR, points added) per QB

### Historical Context

- [ ] **HIST-01**: Combine measurables (speed score, burst score, catch radius) linked to player IDs via name+draft year join
- [ ] **HIST-02**: Draft capital (pick value via trade chart) linked to player IDs

### Infrastructure

- [x] **INFRA-01**: New Silver tables registered in config.py for health checks and download_latest_parquet()
- [ ] **INFRA-02**: Silver team transformation CLI script (separate from player transformation)
- [ ] **INFRA-03**: All new Silver output follows season/week partition convention with timestamped filenames

## Future Requirements

Deferred to v1.3+. Tracked but not in current roadmap.

### Rolling Window Extensions

- **EWM-01**: Exponentially-weighted moving averages as alternative to fixed windows
- **SOS-03**: Forward-looking SOS using remaining schedule

### Gold Integration

- **GOLD-01**: Update projection engine to consume new Silver team metrics
- **GOLD-02**: Update matchup multiplier to use opponent-adjusted EPA instead of raw rankings
- **GOLD-03**: Backtest comparison of projections with vs without new Silver features

## Out of Scope

| Feature | Reason |
|---------|--------|
| Play-level Silver table (PBP copy) | Zero transformation value; query Bronze PBP directly via DuckDB |
| WPA team aggregates | WPA collapses toward zero when summed; EPA is the correct aggregation unit |
| Real-time within-game metrics | Requires streaming infrastructure; batch Parquet pipeline operates on weekly cadence |
| Weather normalization on EPA | ~2pp improvement for high complexity; tag outdoor/dome via roof column instead |
| Positional matchup grades (WR vs CB) | Requires graph joins; deferred to Neo4j Phase 5 |
| Per-play EPA normalization by down/distance | Diverges from nflfastR standard; marginal improvement per research |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PBP-01 | Phase 15 | Complete |
| PBP-02 | Phase 15 | Complete |
| PBP-03 | Phase 15 | Complete |
| PBP-04 | Phase 15 | Complete |
| PBP-05 | Phase 15 | Complete |
| TEND-01 | Phase 15 | Pending |
| TEND-02 | Phase 15 | Pending |
| TEND-03 | Phase 15 | Pending |
| TEND-04 | Phase 15 | Pending |
| INFRA-01 | Phase 15 | Complete |
| INFRA-02 | Phase 15 | Pending |
| INFRA-03 | Phase 15 | Pending |
| SOS-01 | Phase 16 | Pending |
| SOS-02 | Phase 16 | Pending |
| SIT-01 | Phase 16 | Pending |
| SIT-02 | Phase 16 | Pending |
| SIT-03 | Phase 16 | Pending |
| PROF-01 | Phase 17 | Pending |
| PROF-02 | Phase 17 | Pending |
| PROF-03 | Phase 17 | Pending |
| PROF-04 | Phase 17 | Pending |
| PROF-05 | Phase 17 | Pending |
| PROF-06 | Phase 17 | Pending |
| HIST-01 | Phase 18 | Pending |
| HIST-02 | Phase 18 | Pending |

**Coverage:**
- v1.2 requirements: 25 total
- Mapped to phases: 25
- Unmapped: 0

---
*Requirements defined: 2026-03-13*
*Last updated: 2026-03-13 after roadmap creation — traceability complete*
