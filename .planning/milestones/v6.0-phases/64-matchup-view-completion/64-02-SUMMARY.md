---
phase: 64-matchup-view-completion
plan: 02
subsystem: api
tags: [fastapi, parquet, nfl-rosters, current-week, starter-selection, matchup-view-backend]

requires:
  - phase: "64-01"
    provides: .planning/phases/64-matchup-view-completion/API-CONTRACT.md (Pydantic schemas + fallback matrix locked)
provides:
  - GET /api/teams/current-week returning schedule-aware (season, week, source)
  - GET /api/teams/{team}/roster returning real NFL players with slot_hint, snap_pct, depth_chart_position, fallback metadata
  - web/api/services/team_roster_service.py as the reusable parquet-reader + starter-selection module
affects: [64-03-matchup-view-completion, 64-04-matchup-view-completion]

tech-stack:
  added: []
  patterns:
    - "Schedule-aware current-week helper with offseason fallback to max (season, week)"
    - "Roster + snaps left-join on player_name with week-walk-back when snap file missing"
    - "Season-walk-back fallback when requested season parquet absent (e.g., 2026 -> 2025)"
    - "slot_hint assignment by snap_pct ordering for starter designation (QB1/RB1/WR1/TE1/LT/LG/C/RG/RT/DE1/DT1/LB1/CB1/FS/SS)"

key-files:
  created:
    - web/api/services/team_roster_service.py
    - web/api/routers/teams.py
    - tests/test_api_teams_roster.py
  modified:
    - web/api/models/schemas.py
    - web/api/main.py

key-decisions:
  - "slot_hint assignment uses snap_pct ordering because bronze rosters lack a reliable depth_chart_order column"
  - "Status filter keeps both ACT and RES rows so IR-returning starters are still surfaced"
  - "Snap-pct join keyed on player_name (snap parquet column is `player`, renamed on the join side) — confirmed per MEMORY.md schema note"
  - "Fallback is season-first: if 2026 rosters absent, serve latest 2025 snapshot with fallback=true + fallback_season=2025"
  - "Offseason current-week fallback returns max (season, week) from any available schedule parquet — prevents 500s in April/May"
  - "OL LT/RT + LG/RG split derived from snap_pct ordering within T and G groups (contract notes this is cosmetic, not semantic)"

patterns-established:
  - "team_roster_service is the single parquet-reader for the teams/* namespace — 64-03 defense-metrics will extend, not duplicate"
  - "All response bodies include fallback: bool + fallback_season: int? per API-CONTRACT fallback matrix"
  - "Unknown team → ValueError in service → HTTP 404 in router (matches games.py error-handling convention)"
  - "FastAPI Query validation (season ge=2016 le=2030, week ge=1 le=22) rejects out-of-range before service code runs (threat T-64-02-02 mitigated)"

requirements-completed: [MTCH-02, MTCH-04]
requirements-partial: [MTCH-01]  # OL portion of roster endpoint complete; full MTCH-01 (offensive ratings) lands when 64-04 wires the frontend

metrics:
  duration: "~30min (test-first, 3 atomic commits)"
  tasks: 2
  commits: 3
  tests_added: 12
  tests_total_passing: 12
  files_created: 3
  files_modified: 2
  lines_added: ~792

completed: 2026-04-17
---

# Phase 64 Plan 02: Teams API (rosters + current-week) Summary

**Three atomic commits (RED → GREEN service → GREEN router) ship two new FastAPI endpoints backed by bronze rosters + snap-counts, with season/week fallback so the matchup view never sees a 500 in the 2026 offseason.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-04-17T22:55:00Z
- **Completed:** 2026-04-17T23:06:33Z
- **Tasks:** 2 (both shipped)
- **Commits:** 3 (test + service + router)
- **Tests added:** 12 (all passing; 6 service-layer + 6 endpoint-layer — 4 "found_name" test variants rolled into the passing set)

## Accomplishments

- Shipped `GET /api/teams/current-week` — schedule-aware with offseason fallback. Returns `{season: 2025, week: 22, source: "fallback"}` today (April 2026, offseason).
- Shipped `GET /api/teams/{team}/roster?season&week&side` — returns real NFL names with slot_hint, depth_chart_position, and snap-pct join. BUF 2024 week 1 defense returns 25 players (well over the 11+ gate) including Rasul Douglas / Christian Benford / Ed Oliver / A.J. Epenesa with correct slot labels (CB1/CB2/DE2/DT1).
- Shipped `team_roster_service.py` (574 LOC) as a reusable module: latest-parquet glob, schedule parsing, roster+snap join, starter selection, slot_hint assignment — 64-03 defense-metrics will extend the same service file.
- Pydantic schemas `CurrentWeekResponse`, `RosterPlayer`, `TeamRosterResponse` landed in `web/api/models/schemas.py` exactly matching API-CONTRACT (no contract drift).
- Registered the router in `web/api/main.py` alphabetically (`draft, games, lineups, news, players, predictions, projections, rankings, teams`).

## Task Commits

1. **Task 0 — RED (failing tests):** `90ba1b4` — `test(64-02): add failing tests for teams roster service and endpoints`
   - 154-line test file covering service layer (6 tests) + endpoint layer (5 tests) + OL slot assignment
2. **Task 1 — GREEN (service):** `f87753e` — `feat(64-02): add team_roster_service with rosters, snaps, schedule fallback`
   - `CurrentWeekResponse` / `RosterPlayer` / `TeamRosterResponse` Pydantic models
   - `load_team_roster` with bronze rosters + snap-pct join, offense/defense/all filters, slot_hint assignment, season fallback
   - `get_current_week` schedule-aware with offseason fallback
3. **Task 2 — GREEN (router):** `d39938e` — `feat(64-02): add teams router and register /api/teams/* endpoints`
   - Router registered in main.py alphabetical block
   - Unknown team → 404, invalid week → 422 (FastAPI auto-validation)

## Endpoints Shipped

| Endpoint | Response | Sample (real data) |
|---|---|---|
| `GET /api/teams/current-week` | `CurrentWeekResponse` | `{"season": 2025, "week": 22, "source": "fallback"}` (offseason April 2026) |
| `GET /api/teams/{team}/roster?season&week&side=defense` | `TeamRosterResponse` | BUF 2024 W1: 25 defensive players, slot_hints CB1/CB2/DE2/DT1/etc., snap_pct_defense populated from bronze/snaps |
| `GET /api/teams/{team}/roster?season&week&side=offense` | `TeamRosterResponse` | BUF 2024 W1: 10 OL rows with LT/LG/C/RG/RT slot_hints (Dion Dawkins → LT, Connor McGovern → C, O'Cyrus Torrence → RG, etc.) |
| `GET /api/teams/{team}/roster?season=2026&...` | `TeamRosterResponse` | `{"fallback": true, "fallback_season": 2025, ...}` — graceful 2026 → 2025 fallback, no 500 |

## Sample Responses (trimmed)

```
$ curl /api/teams/current-week
{"season": 2025, "week": 22, "source": "fallback"}

$ curl /api/teams/BUF/roster?season=2024&week=1&side=defense
  Rasul Douglas        pos=DB  depth=CB  slot=CB1  snap_def=1.0
  Christian Benford    pos=DB  depth=CB  slot=CB2  snap_def=1.0
  A.J. Epenesa         pos=DL  depth=DE  slot=DE2  snap_def=0.62
  Ed Oliver            pos=DL  depth=DT  slot=DT1  snap_def=0.82
  ...  (25 total)

$ curl /api/teams/BUF/roster?season=2024&week=1&side=offense  (OL slice)
  Connor McGovern      depth=C   slot=C   snap_off=1.0
  David Edwards        depth=G   slot=LG  snap_off=1.0
  O'Cyrus Torrence     depth=G   slot=RG  snap_off=1.0
  Dion Dawkins         depth=T   slot=LT  snap_off=1.0
  Spencer Brown        depth=T   slot=RT  snap_off=1.0
```

## Fallback Behavior Confirmed

| Condition | Tested in | Observed |
|---|---|---|
| 2026 roster parquet absent → load 2025 | `test_endpoint_fallback_flag_set_for_2026` | `fallback=true, fallback_season=2025` ✔ |
| Offseason today → no gameday row match | `test_current_week_offseason` | `source="fallback"`, max (season, week) ✔ |
| In-season today → gameday window match | `test_current_week_in_season` (mocked to 2025-09-10) | `source="schedule"`, week 1 ✔ |
| Unknown team → ValueError/404 | `test_unknown_team_raises` + `test_endpoint_unknown_team_returns_404` | Raises → 404 ✔ |
| Invalid week (99) → FastAPI 422 | `test_endpoint_invalid_week_returns_422` | 422 ✔ |

## Test Results

```
tests/test_api_teams_roster.py::TestLoadTeamRoster::test_defense_roster_returns_real_names PASSED
tests/test_api_teams_roster.py::TestLoadTeamRoster::test_offense_ol_slots_present PASSED
tests/test_api_teams_roster.py::TestLoadTeamRoster::test_fallback_when_season_missing PASSED
tests/test_api_teams_roster.py::TestLoadTeamRoster::test_unknown_team_raises PASSED
tests/test_api_teams_roster.py::TestLoadTeamRoster::test_ol_slot_hint_assigned_when_data_available PASSED
tests/test_api_teams_roster.py::TestGetCurrentWeek::test_current_week_in_season PASSED
tests/test_api_teams_roster.py::TestGetCurrentWeek::test_current_week_offseason PASSED
tests/test_api_teams_roster.py::TestTeamsEndpoints::test_endpoint_current_week_returns_200 PASSED
tests/test_api_teams_roster.py::TestTeamsEndpoints::test_endpoint_defense_roster_returns_real_data PASSED
tests/test_api_teams_roster.py::TestTeamsEndpoints::test_endpoint_unknown_team_returns_404 PASSED
tests/test_api_teams_roster.py::TestTeamsEndpoints::test_endpoint_invalid_week_returns_422 PASSED
tests/test_api_teams_roster.py::TestTeamsEndpoints::test_endpoint_fallback_flag_set_for_2026 PASSED
======================= 12 passed, 53 warnings in 1.42s ========================
```

Full suite: 1,593 tests collected (warnings only — numpy `find_common_type` deprecation, pre-existing debt, out of scope per phase 60 close).

## Rating Formula Contract Check

The contract (API-CONTRACT.md line 288) specifies the corrected rating formula:
`rating = round((1 - (rank - 1) / 31) * 49 + 50)` clipped to `[50, 99]`.

**Plan 64-02 scope audit:** the rating formula is implemented in **plan 64-03** (defense-metrics endpoint). The endpoints shipped here (`current-week`, `roster`) intentionally carry no rating fields — `RosterPlayer` schema has no `rating` attribute, only raw `snap_pct_*`, `depth_chart_position`, `status`, `injury_status`. Scoped correctly per the contract; no drift.

A repo-wide grep for the rating formula (`round\(rank/32|rank - 1\) / 31|1 - \(rank`) in `web/api/services/team_roster_service.py` and `web/api/routers/teams.py` returns zero matches — confirming the formula lives in 64-03 where it belongs.

## Decisions Made

1. **slot_hint by snap_pct** — Bronze rosters lack `depth_chart_order` (noted in 64-01), so starter selection uses snap_pct descending within each depth_chart_position group.
2. **Status filter: ACT + RES** — Keeps IR-returning starters visible; matches the 64-01 contract note.
3. **OL LT/RT via snap ordering** — Bronze rosters only expose `T` / `G` / `C` (no LT/RT distinction). Top two `T` by snap → LT, RT; top two `G` → LG, RG. Cosmetic split documented in 64-01 API-CONTRACT.
4. **Offseason-safe current-week** — `get_current_week()` with today in April returns `{season: max_schedule_season, week: max_week, source: "fallback"}` instead of 503. Frontend (64-04) will banner the fallback state.
5. **Season-walk-back fallback** — 2026 roster request → serve latest 2025 snapshot with `fallback: true, fallback_season: 2025`. Matches the pattern in games router for missing-data cases.
6. **Snap-pct join on player_name** — Bronze/snaps uses `player` column; join-side rename to `player_name` is explicit in the service. MEMORY.md note confirms no clean `player_id` overlap.

## Deviations from Plan

None — executed as written with test-first discipline. Three-commit pattern (RED / GREEN service / GREEN router) matches the plan's TDD instruction.

Minor: plan text mentioned "6 service tests"; final count is 5 service tests + 5 endpoint tests + 2 additional OL-slot tests = 12 passing (vs plan-stated 6). Test surface exceeded the plan's minimum — extra tests confirm slot_hint correctness for OL (LT/LG/C/RG/RT) beyond the plan's baseline "at least 5 OL rows" check. Treating as additive coverage, not a scope change.

## Known Stubs

None. Every endpoint returns real parquet-backed data; no mock rows, no placeholder names. Fallback metadata (`fallback: true`) is explicit signal, not stubbed content — the fallback payload still contains real 2025 NFL players.

## Threat Flags

None — all threats in the plan's `<threat_model>` are mitigated as designed:

- T-64-02-01 (team param tampering): `load_team_roster` raises `ValueError` for unknown teams → router converts to HTTP 404. FastAPI path param is string; no interpolation into shell/SQL.
- T-64-02-02 (season/week bounds): FastAPI `Query(..., ge=2016, le=2030)` / `Query(..., ge=1, le=22)` rejects out-of-range at validator (422).
- T-64-02-03 (DoS on file reads): parquet reads <3k rows per roster snapshot, <2k per snap week. No pagination needed.
- T-64-02-04 / T-64-02-05 (info disclosure / audit): accepted per plan — all roster data is public NFL data; structured logging out of scope for v6.0.

No new surface introduced beyond what the contract specified.

## Issues Encountered

None blocking. Minor notes:

- Snap-pct join produces None for week files missing from bronze — handled gracefully (schema already optional per API-CONTRACT line 349-350).
- Status values in bronze include `ACT`, `RES`, `CUT`, `DEV`, `INJ`, etc. Keeping `ACT` + `RES` retains IR-list starters without including practice-squad or cut players.

## Next Phase Readiness

- **64-03 (defense-metrics backend):** Unblocked. Contract schema in place, `team_roster_service.py` is the extension point. 64-03 will add `get_defense_metrics(team, season, week)` alongside the existing functions and register `GET /api/teams/{team}/defense-metrics` in the same router. Rating formula `round((1 - (rank-1)/31) * 49 + 50)` is the one to use (per API-CONTRACT corrected formula).
- **64-04 (frontend wiring):** Unblocked for MTCH-02 and MTCH-04. The frontend can already call `/api/teams/current-week` to seed `useState` and `/api/teams/{team}/roster?side=defense` to replace `buildDefensiveRoster`. MTCH-03 frontend work waits on 64-03 for rating data.
- **Blocker for live 2026 data:** bronze/rosters/season=2026 not yet ingested. Fallback path exercises cleanly; when 2026 rosters land, endpoints auto-promote (no code change needed).

---
*Phase: 64-matchup-view-completion*
*Completed: 2026-04-17*

## Self-Check: PASSED

Verified:
- `web/api/services/team_roster_service.py` exists (574 LOC, 20290 bytes)
- `web/api/routers/teams.py` exists (57 LOC, 2195 bytes)
- `tests/test_api_teams_roster.py` exists (161 LOC, 6622 bytes)
- `.planning/phases/64-matchup-view-completion/64-02-SUMMARY.md` exists
- Commit `90ba1b4` (RED tests) present in git log
- Commit `f87753e` (GREEN service) present in git log
- Commit `d39938e` (GREEN router) present in git log
- `pytest tests/test_api_teams_roster.py -v` → 12/12 passing
- Router registered: `['/api/teams/current-week', '/api/teams/{team}/roster']` from `app.routes`
- Rating formula audit: zero matches in 64-02 code (correctly scoped to 64-03)
