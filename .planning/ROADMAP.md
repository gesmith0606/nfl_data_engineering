# Roadmap: NFL Data Engineering Platform

## Milestones

- ✅ **v1.0 Bronze Expansion** — Phases 1-7 (shipped 2026-03-08)
- ✅ **v1.1 Bronze Backfill** — Phases 8-14 (shipped 2026-03-13)
- ✅ **v1.2 Silver Expansion** — Phases 15-19 (shipped 2026-03-15)
- 🚧 **v1.3 Prediction Data Foundation** — Phases 20-23 (in progress)

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

<details>
<summary>✅ v1.2 Silver Expansion (Phases 15-19) — SHIPPED 2026-03-15</summary>

- [x] Phase 15: PBP Team Metrics and Tendencies (3/3 plans) — completed 2026-03-14
- [x] Phase 16: Strength of Schedule and Situational Splits (2/2 plans) — completed 2026-03-14
- [x] Phase 17: Advanced Player Profiles (2/2 plans) — completed 2026-03-14
- [x] Phase 18: Historical Context (2/2 plans) — completed 2026-03-15
- [x] Phase 19: v1.2 Tech Debt Cleanup (1/1 plan) — completed 2026-03-15

Full details: `.planning/milestones/v1.2-ROADMAP.md`

</details>

### 🚧 v1.3 Prediction Data Foundation (In Progress)

**Milestone Goal:** Expand the Silver layer with penalty, turnover, special teams, weather, rest/travel, coaching, referee, and playoff context features — completing the prediction data foundation for future ML model work.

- [x] **Phase 20: Infrastructure and Data Expansion** — Expand PBP columns, ingest officials data, add stadium coordinates (completed 2026-03-16)
- [ ] **Phase 21: PBP-Derived Team Metrics** — Penalties, turnovers, special teams, red zone trips, sack rates, explosives, drive efficiency, 3rd down, TOP with rolling windows
- [ ] **Phase 22: Schedule-Derived Context** — Weather, rest/travel, coaching changes via new game_context module
- [ ] **Phase 23: Cross-Source Features and Integration** — Referee tendencies, playoff context, pipeline health for all new Silver paths

## Phase Details

### Phase 20: Infrastructure and Data Expansion
**Goal**: All Bronze data needed for v1.3 features is available — expanded PBP columns expose penalty, fumble recovery, and special teams fields; officials data is ingested; stadium coordinates are configured
**Depends on**: Nothing (first phase of v1.3)
**Requirements**: INFRA-01, INFRA-02, INFRA-03
**Success Criteria** (what must be TRUE):
  1. PBP Bronze parquet files for 2016-2025 contain penalty detail columns (`penalty_type`, `penalty_yards`, `penalty_team`), fumble recovery columns (`fumble_recovery_1_team`), and special teams columns (`field_goal_result`, `kick_distance`, punt columns) — verified by loading a sample file and confirming column presence
  2. Officials Bronze data exists locally for 2016-2025 with referee crew assignments per game, accessible via the standard `download_latest_parquet()` pattern
  3. Stadium coordinates for all 32 NFL teams (plus international venues) are available as a config lookup, with latitude/longitude values that produce sensible haversine distances (e.g., NYJ-to-LAR approximately 2,450 miles)
  4. Existing Silver pipeline (team_analytics, player_analytics) still passes all 289 tests with no regressions from the PBP column expansion
**Plans**: 2 plans

Plans:
- [ ] 20-01-PLAN.md — Config expansion (PBP columns, stadium coordinates, officials wiring) + unit tests
- [ ] 20-02-PLAN.md — PBP re-ingestion (2016-2025) and officials ingestion + full regression suite

### Phase 21: PBP-Derived Team Metrics
**Goal**: Eleven new team-level metrics are computed from PBP data with rolling windows and written as Silver parquet — penalties, opponent-drawn penalties, turnover luck, red zone trip volume, special teams FG/punt/return, 3rd down rates, explosive plays, drive efficiency, sack rates, and time of possession
**Depends on**: Phase 20
**Requirements**: PBP-01, PBP-02, PBP-03, PBP-04, PBP-05, PBP-06, PBP-07, PBP-08, PBP-09, PBP-10, PBP-11, INTEG-02
**Success Criteria** (what must be TRUE):
  1. Running `silver_team_transformation.py` produces new Silver parquet files containing all eleven PBP-derived metric categories per team per week for 2016-2025
  2. Every new metric has `_roll3`, `_roll6`, and `_std` rolling window variants computed with `shift(1)` lag to prevent look-ahead bias
  3. Penalty metrics use the `penalty == 1` flag (not `play_type == 'penalty'`), special teams metrics use a dedicated ST play-type filter (not `_filter_valid_plays()`), and red zone trips use drive-level grouping producing 3-5 trips per team per game (not 15+ from play-level counting)
  4. All new functions in `team_analytics.py` have unit tests, and existing tests remain green
  5. New Silver output paths follow the existing `teams/` naming convention and are readable via `download_latest_parquet()`
**Plans**: TBD

Plans:
- [ ] 21-01: TBD
- [ ] 21-02: TBD
- [ ] 21-03: TBD

### Phase 22: Schedule-Derived Context
**Goal**: Weather, rest/travel, and coaching features are extracted from schedules Bronze into a new game_context Silver module with per-team per-week granularity
**Depends on**: Phase 20
**Requirements**: SCHED-01, SCHED-02, SCHED-03, SCHED-04, SCHED-05
**Success Criteria** (what must be TRUE):
  1. A new `src/game_context.py` module exists with an `_unpivot_schedules()` helper that converts home/away game rows into per-team rows, and a new `silver_game_context_transformation.py` script produces Silver parquet under `teams/game_context/`
  2. Weather columns include temperature, wind speed, roof type, surface type, and derived flags (`is_dome`, `is_high_wind` for wind > 15 mph) — dome games receive neutral weather values
  3. Rest/travel columns include days since last game (capped at 14), `is_post_bye`, `is_short_rest`, `rest_advantage`, travel distance (haversine miles), and time zone differential — Week 1 rest capped correctly
  4. Coaching columns include head coach name per team per week, `coaching_change` flag detecting mid-season and off-season HC changes, and coaching tenure in weeks
  5. All game_context features are joinable on `[team, season, week]` to existing Silver data
**Plans**: TBD

Plans:
- [ ] 22-01: TBD
- [ ] 22-02: TBD

### Phase 23: Cross-Source Features and Integration
**Goal**: Referee tendency profiles and playoff/elimination context are computed by joining data across Silver modules, and pipeline health monitoring covers all new v1.3 Silver paths
**Depends on**: Phase 21, Phase 22
**Requirements**: CROSS-01, CROSS-02, INTEG-01
**Success Criteria** (what must be TRUE):
  1. Referee tendency profiles show historical penalty rate, scoring impact, and home bias per crew — computed by joining schedules referee data with penalty Silver metrics, with referee name normalization producing 20-25 unique active referees per season (not 50+ from name variants)
  2. Playoff/elimination context columns include `wins`, `losses`, `win_pct`, `division_rank`, `games_behind_division_leader`, and `late_season_contention` — computed via cumulative sum with `shift(1)` lag, handling ties as W-L-T, and spot-checked against published standings for at least 2 historical seasons
  3. `check_pipeline_health.py` validates all new Silver output paths with freshness and file size checks
  4. A test assembles the full prediction feature vector (~130 columns) from all Silver sources via left joins on `[team, season, week]` without join errors or unexpected nulls
**Plans**: TBD

Plans:
- [ ] 23-01: TBD
- [ ] 23-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 20 → 21 → 22 → 23
Note: Phases 21 and 22 can execute in parallel (both depend only on Phase 20).

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
| 19. v1.2 Tech Debt Cleanup | v1.2 | 1/1 | Complete | 2026-03-15 |
| 20. Infrastructure and Data Expansion | 2/2 | Complete   | 2026-03-16 | - |
| 21. PBP-Derived Team Metrics | v1.3 | 0/3 | Not started | - |
| 22. Schedule-Derived Context | v1.3 | 0/2 | Not started | - |
| 23. Cross-Source Features and Integration | v1.3 | 0/2 | Not started | - |

---
*Roadmap created: 2026-03-08*
*Last updated: 2026-03-16 after Phase 20 planning completed*
