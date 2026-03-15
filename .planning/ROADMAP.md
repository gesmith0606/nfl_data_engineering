# Roadmap: NFL Data Engineering Platform

## Milestones

- ✅ **v1.0 Bronze Expansion** — Phases 1-7 (shipped 2026-03-08)
- ✅ **v1.1 Bronze Backfill** — Phases 8-14 (shipped 2026-03-13)
- [ ] **v1.2 Silver Expansion** — Phases 15-19 (in progress)

## Phases

<details>
<summary>✅ v1.0 Bronze Expansion (Phases 1-7) — SHIPPED 2026-03-08</summary>

- [x] Phase 1: Infrastructure Prerequisites (2/2 plans) — completed 2026-03-08
- [x] Phase 2: Core PBP Ingestion (1/1 plan) — completed 2026-03-08
- [x] Phase 3: Advanced Stats & Context Data (2/2 plans) — completed 2026-03-08
- [x] Phase 4: Documentation Update (3/3 plans) — completed 2026-03-08
- [x] Phase 5: Phase 1 Verification Backfill (1/1 plan) — completed 2026-03-08
- [x] Phase 6: Wire Bronze Validation (1/1 plan) — completed 2026-03-08
- [x] Phase 7: Tech Debt Cleanup (1/1 plan) — completed 2026-03-08

Full details: `.planning/milestones/v1.0-ROADMAP.md`

</details>

<details>
<summary>✅ v1.1 Bronze Backfill (Phases 8-14) — SHIPPED 2026-03-13</summary>

- [x] Phase 8: Pre-Backfill Guards (1/1 plan) — completed 2026-03-09
- [x] Phase 9: New Data Type Ingestion (3/3 plans) — completed 2026-03-09
- [x] Phase 10: Existing Type Backfill (2/2 plans) — completed 2026-03-12
- [x] Phase 11: Orchestration and Validation (2/2 plans) — completed 2026-03-12
- [x] Phase 12: 2025 Player Stats Gap Closure (2/2 plans) — completed 2026-03-13
- [x] Phase 13: Bronze-Silver Path Alignment (1/1 plan) — completed 2026-03-13
- [x] Phase 14: Bronze Cosmetic Cleanup (1/1 plan) — completed 2026-03-13

Full details: `.planning/milestones/v1.1-ROADMAP.md`

</details>

### v1.2 Silver Expansion (In Progress)

**Milestone Goal:** Expand Silver layer with PBP-derived team analytics, strength of schedule, situational splits, advanced player profiles, and historical context — all with rolling windows — to feed game prediction models and improve fantasy projections.

- [x] **Phase 15: PBP Team Metrics and Tendencies** - Team EPA, success rate, CPOE, red zone efficiency, pace, PROE, 4th down aggressiveness from PBP with rolling windows; fix existing rolling window bug; new Silver CLI and config registration (completed 2026-03-14)
- [x] **Phase 16: Strength of Schedule and Situational Splits** - Opponent-adjusted EPA rankings and schedule difficulty; home/away, divisional, and game script performance splits with rolling windows (completed 2026-03-14)
- [x] **Phase 17: Advanced Player Profiles** - NGS separation/RYOE/TTT, PFR pressure/blitz rates, QBR rolling windows per player-week via new advanced analytics module (completed 2026-03-14)
- [x] **Phase 18: Historical Context** - Combine measurables and draft capital linked to player IDs as a static dimension table for rookie/breakout modeling (completed 2026-03-15)
- [ ] **Phase 19: v1.2 Tech Debt Cleanup** - Close audit gaps: wire health check for 6 new Silver paths, use config constants in silver_team_transformation.py, fix deferred import, document historical partition exception

## Phase Details

### Phase 15: PBP Team Metrics and Tendencies
**Goal**: Users can generate PBP-derived team performance and tendency metrics with rolling windows for any season 2016-2025 via a new Silver team CLI
**Depends on**: Phase 14 (Bronze layer complete with PBP data)
**Requirements**: PBP-01, PBP-02, PBP-03, PBP-04, PBP-05, TEND-01, TEND-02, TEND-03, TEND-04, INFRA-01, INFRA-02, INFRA-03
**Success Criteria** (what must be TRUE):
  1. Running `silver_team_transformation.py --seasons 2024` produces Parquet files at `data/silver/teams/pbp_metrics/season=2024/` containing EPA/play, success rate, CPOE, red zone efficiency per team-week with 3-game and 6-game rolling columns
  2. The same CLI run produces team tendency metrics (pace, PROE, 4th down aggressiveness, early-down run rate) with rolling windows in `data/silver/teams/tendencies/season=2024/`
  3. Rolling windows in both new and existing Silver modules group by (entity, season) so that Week 1 rolling values are NaN (not contaminated by prior season)
  4. All new Silver output paths are registered in `config.py` and retrievable via `download_latest_parquet()`
  5. Playoff weeks are excluded from all team metrics (max week in output is 18)
**Plans:** 3/3 plans complete
Plans:
- [ ] 15-01-PLAN.md -- Fix rolling window bug, register config paths, create team_analytics.py skeleton
- [ ] 15-02-PLAN.md -- PBP performance metrics (EPA, success rate, CPOE, red zone) with tests
- [ ] 15-03-PLAN.md -- Tendency metrics (pace, PROE, 4th down, early-down), CLI script, data dictionary

### Phase 16: Strength of Schedule and Situational Splits
**Goal**: Users can see opponent-adjusted team rankings and situational performance splits that account for schedule difficulty and game context
**Depends on**: Phase 15 (requires team EPA outputs)
**Requirements**: SOS-01, SOS-02, SIT-01, SIT-02, SIT-03
**Success Criteria** (what must be TRUE):
  1. Running the team CLI produces SOS output at `data/silver/teams/sos/` with opponent-adjusted EPA and schedule difficulty rankings (1-32) per team per week, using only lagged (week N-1) opponent strength
  2. Week 1 opponent-adjusted EPA equals raw EPA for all teams (no circular dependency)
  3. Situational splits at `data/silver/teams/situational/` contain home/away, divisional/non-divisional tags, and game script splits (leading/trailing by 7+) with rolling EPA
  4. Running the same CLI twice on identical input produces identical output (idempotency)
**Plans:** 2/2 plans complete
Plans:
- [ ] 16-01-PLAN.md -- Config updates (TEAM_DIVISIONS, S3 keys) and SOS computation with tests
- [ ] 16-02-PLAN.md -- Situational splits (home/away, divisional, game script) and CLI wiring

### Phase 17: Advanced Player Profiles
**Goal**: Users can generate NGS, PFR, and QBR-derived player profile metrics with rolling windows for enhanced QB, RB, WR, and TE evaluation
**Depends on**: Phase 15 (infrastructure patterns established; independent of SOS/situational data)
**Requirements**: PROF-01, PROF-02, PROF-03, PROF-04, PROF-05, PROF-06
**Success Criteria** (what must be TRUE):
  1. Running `silver_advanced_transformation.py --seasons 2024` produces advanced player profiles at `data/silver/players/advanced/season=2024/` with NGS WR/TE separation and catch probability, QB time-to-throw and aggressiveness, and RB rush yards over expected — all with rolling windows
  2. PFR pressure rate per QB and blitz rate per defensive team are included with rolling windows
  3. QBR rolling windows (total QBR, points added) are included per QB
  4. Players without advanced stats are preserved in output via left-join (no silent row drops); NaN coverage is logged at write time
  5. Sparse columns use `min_periods=3` for rolling averages to require meaningful history before producing values
**Plans:** 2/2 plans complete
Plans:
- [ ] 17-01-PLAN.md -- Config registration, player_advanced_analytics.py module with all 6 compute functions and tests
- [ ] 17-02-PLAN.md -- silver_advanced_transformation.py CLI with join orchestration and full-season output

### Phase 18: Historical Context
**Goal**: Users can access combine measurables and draft capital linked to player IDs for rookie evaluation and breakout modeling
**Depends on**: Phase 15 (infrastructure patterns; independent of Phases 16-17)
**Requirements**: HIST-01, HIST-02
**Success Criteria** (what must be TRUE):
  1. A static dimension table at `data/silver/players/historical/combine_draft_profiles.parquet` contains combine measurables (speed score, burst score, catch radius) and draft capital (pick value via trade chart) linked to player IDs
  2. The join uses pfr_id matching and logs unmatched players with match rate metrics; row count after join equals row count before join (no explosion)
**Plans:** 2/2 plans complete
Plans:
- [ ] 18-01-PLAN.md -- Config registration, historical_profiles.py compute module with tests
- [ ] 18-02-PLAN.md -- silver_historical_transformation.py CLI with end-to-end pipeline

### Phase 19: v1.2 Tech Debt Cleanup
**Goal**: Close all integration and flow gaps identified by the v1.2 milestone audit — wire health monitoring for new Silver paths, eliminate hard-coded S3 paths, fix deferred import, document partition exception
**Depends on**: Phase 18 (all feature phases complete)
**Requirements**: INFRA-01, INFRA-03, PROF-05 (gap closure — requirements already satisfied, fixing implementation quality)
**Gap Closure:** Closes gaps from v1.2-MILESTONE-AUDIT.md
**Success Criteria** (what must be TRUE):
  1. `check_pipeline_health.py` monitors all 6 new Silver paths (teams/pbp_metrics, teams/tendencies, teams/sos, teams/situational, players/advanced, players/historical)
  2. `silver_team_transformation.py` imports and uses `SILVER_TEAM_S3_KEYS` from `config.py` instead of hard-coded f-strings
  3. `player_advanced_analytics.py` uses top-level import of `apply_team_rolling` instead of deferred import
  4. Historical profiles partition exception is documented in code comment
Plans:
- [ ] 19-01-PLAN.md -- All tech debt fixes (health check paths, config imports, deferred import, partition docs)

## Progress

**Execution Order:**
Phases execute in numeric order: 15 -> 16 -> 17 -> 18

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Infrastructure Prerequisites | v1.0 | 2/2 | Complete | 2026-03-08 |
| 2. Core PBP Ingestion | v1.0 | 1/1 | Complete | 2026-03-08 |
| 3. Advanced Stats & Context Data | v1.0 | 2/2 | Complete | 2026-03-08 |
| 4. Documentation Update | v1.0 | 3/3 | Complete | 2026-03-08 |
| 5. Phase 1 Verification Backfill | v1.0 | 1/1 | Complete | 2026-03-08 |
| 6. Wire Bronze Validation | v1.0 | 1/1 | Complete | 2026-03-08 |
| 7. Tech Debt Cleanup | v1.0 | 1/1 | Complete | 2026-03-08 |
| 8. Pre-Backfill Guards | v1.1 | 1/1 | Complete | 2026-03-09 |
| 9. New Data Type Ingestion | v1.1 | 3/3 | Complete | 2026-03-09 |
| 10. Existing Type Backfill | v1.1 | 2/2 | Complete | 2026-03-12 |
| 11. Orchestration and Validation | v1.1 | 2/2 | Complete | 2026-03-12 |
| 12. 2025 Player Stats Gap Closure | v1.1 | 2/2 | Complete | 2026-03-13 |
| 13. Bronze-Silver Path Alignment | v1.1 | 1/1 | Complete | 2026-03-13 |
| 14. Bronze Cosmetic Cleanup | v1.1 | 1/1 | Complete | 2026-03-13 |
| 15. PBP Team Metrics and Tendencies | v1.2 | 3/3 | Complete | 2026-03-14 |
| 16. Strength of Schedule and Situational Splits | v1.2 | 2/2 | Complete | 2026-03-14 |
| 17. Advanced Player Profiles | v1.2 | 2/2 | Complete | 2026-03-14 |
| 18. Historical Context | v1.2 | 2/2 | Complete | 2026-03-15 |
| 19. v1.2 Tech Debt Cleanup | v1.2 | 0/1 | Planned | - |

---
*Roadmap created: 2026-03-08*
*Last updated: 2026-03-15 after Phase 18 planning*
