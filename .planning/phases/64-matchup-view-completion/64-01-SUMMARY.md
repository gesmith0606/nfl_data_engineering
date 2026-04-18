---
phase: 64-matchup-view-completion
plan: 01
subsystem: api
tags: [fastapi, parquet, nfl-rosters, defense-metrics, frontend-contract, matchup-view]

requires:
  - phase: "defd6cc initial matchup view ship"
    provides: web/frontend/src/features/nfl/components/matchup-view.tsx (placeholders to be replaced)
provides:
  - PLACEHOLDER-INVENTORY.md cataloguing every fake value in matchup-view.tsx
  - API-CONTRACT.md locking 3 endpoints (current-week, roster, defense-metrics) with Pydantic schemas + fallback matrix
affects: [64-02-matchup-view-completion, 64-03-matchup-view-completion, 64-04-matchup-view-completion]

tech-stack:
  added: []
  patterns:
    - "Contract-first endpoint design — frontend and backend plans target a locked schema"
    - "Multi-tier fallback matrix per endpoint (missing season → missing week → missing positional)"
    - "Roster + snaps left-join on player_name for starter selection"

key-files:
  created:
    - .planning/phases/64-matchup-view-completion/PLACEHOLDER-INVENTORY.md
    - .planning/phases/64-matchup-view-completion/API-CONTRACT.md
  modified: []

key-decisions:
  - "2026 data absent locally — all endpoints return `fallback: true` and use latest 2025 snapshot until bronze/silver refreshes"
  - "Defensive slot ratings are team-level, not per-player (positional rank from silver/defense/positional) — documented as a known limitation vs. PFF-grade data"
  - "Corrected rating formula: rating = round((1 - (rank-1)/31) * 49 + 50) ∈ [50,99]; plan text had inverted form (101 - ...) which produced rank=1 → 49"
  - "OL slot labels (LT/RT/LG/RG) are derived by snap-pct ordering because roster only exposes 'T' and 'G' — LT vs RT distinction is cosmetic"
  - "Starter selection uses snap_pct (not depth_chart_order — that column does not exist in bronze rosters)"

patterns-established:
  - "Every new endpoint exposes a `fallback: bool` + `fallback_season: int?` so the frontend can banner offseason/missing-data states"
  - "All parquet reads use `download_latest_parquet()` from `src/utils.py` per CLAUDE.md S3 Read Rule"
  - "Pydantic response models colocated in web/api/models/schemas.py — plans 64-02/64-03 paste the schema block unchanged"

requirements-completed: []

duration: 38min
completed: 2026-04-17
---

# Phase 64 Plan 01: Placeholder Inventory + API Contract Summary

**Line-level audit of matchup-view.tsx placeholders mapped to three new API endpoints (current-week / roster / defense-metrics) with Pydantic schemas and fallback matrix locked for parallel execution in 64-02/64-03/64-04.**

## Performance

- **Duration:** 38 min
- **Started:** 2026-04-17T18:19:00Z
- **Completed:** 2026-04-17T18:57:00Z
- **Tasks:** 2
- **Files created:** 2

## Accomplishments

- Catalogued **5 distinct placeholders** in `matchup-view.tsx` covering all 4 MTCH requirements (MTCH-01..04)
- Audited data lake and **confirmed the 2026 data gap** (no schedules, rosters, snaps, defense, or SOS files for season=2026); recommended 2025 max-week fallback
- Locked 3 endpoint contracts with full Pydantic schemas, query params, error modes, data source column mappings, and a per-endpoint fallback matrix
- Surfaced a **bug in the plan text**: the defense rating formula `rating = 101 - round(rank/32 * 49 + 50)` maps rank=1 to 49 (not 99). Corrected to `round((1 - (rank-1)/31) * 49 + 50)` in the contract doc so 64-03 implements the right formula
- Documented roster-schema surprises: `depth_chart_order` does not exist (plan assumed it did); only `T` and `G` OL positions (no `LT/RT` granularity); status filter must include `RES` in addition to `ACT`

## Task Commits

1. **Task 1: Write PLACEHOLDER-INVENTORY.md** — `c7c02a1` (docs)
2. **Task 2: Write API-CONTRACT.md** — `cab57ca` (docs)

## Files Created/Modified

- `.planning/phases/64-matchup-view-completion/PLACEHOLDER-INVENTORY.md` — 5-row catalogue of placeholders + Data Availability section + Summary Table mapping each symbol to MTCH-XX
- `.planning/phases/64-matchup-view-completion/API-CONTRACT.md` — 3 endpoint specs (GET `/api/teams/current-week`, GET `/api/teams/{team}/roster`, GET `/api/teams/{team}/defense-metrics`), Pydantic schemas, fallback matrix, requirements coverage table

## Endpoints Locked

| Endpoint | Implements | Primary data source |
|---|---|---|
| `GET /api/teams/current-week` | MTCH-04 | `data/bronze/schedules/season=YYYY/schedules_*.parquet` |
| `GET /api/teams/{team}/roster?season=YYYY&week=WW&side=offense\|defense\|all` | MTCH-01 (OL), MTCH-02 (defense) | `data/bronze/players/rosters/` + `data/bronze/players/snaps/` left-join on `player_name` |
| `GET /api/teams/{team}/defense-metrics?season=YYYY&week=WW` | MTCH-03 | `data/silver/defense/positional/` + `data/silver/teams/sos/` |

## MTCH-XX Coverage Map

| Requirement | Placeholder(s) | Endpoint |
|---|---|---|
| MTCH-01 — Offensive roster shows real ratings | `buildOffensiveRoster` OL branch (lines 162-175); `computeRatings` asymmetry (103-137) | Endpoint B `side=offense` |
| MTCH-02 — Defensive roster uses real NFL data | `buildDefensiveRoster` + `slotHash` (709-750) | Endpoint B `side=defense` |
| MTCH-03 — Matchup advantages from real data | `buildDefensiveRoster` (ratings), `getAdvantage` map (362-391), `MatchupAdvantages` (574-645) | Endpoint C |
| MTCH-04 — Schedule-aware default week | `useState(2026)` / `useState(1)` (783-784) | Endpoint A |

## Decisions Made

1. **Team-level defense ratings (not per-player)** — Silver `avg_pts_allowed` is keyed on `(team, position, week)`, not individual defenders. Secondary slots (CB1/CB2/SS/FS) share the team's WR-allowed rank. Documented as known limitation; PFF subscription would fix it (out of scope per REQUIREMENTS).
2. **Corrected defense rating formula** — Plan text had `rating = 101 - round(rank/32 * 49 + 50)` which maps rank=1 → 49. Contract uses `rating = round((1 - (rank-1)/31) * 49 + 50)` → rank=1 → 99, rank=32 → 50.
3. **Fallback-first contract** — Every endpoint returns `fallback: bool` so the frontend can banner _"Showing Week 22 of 2025 (2026 season not yet available)"_ without special-case error paths.
4. **OL starter selection via snaps, not jersey numbers** — Roster `depth_chart_position` only has `T`, `G`, `C`. Top two `T` by `offense_pct` → LT/RT; top two `G` → LG/RG. LT vs RT ordering is cosmetic (can't be derived from roster alone).
5. **No source-code edits** — Pure documentation plan. `web/frontend/src/features/nfl/components/matchup-view.tsx` untouched; no new routers, schemas, or services created. 64-02 and 64-03 will do the backend work; 64-04 does the frontend wiring.

## Deviations from Plan

None — plan executed exactly as written with one minor correction noted above (rating formula bug caught during contract drafting, fixed in the contract doc itself; not a deviation from plan action, just an improvement over plan text).

## Issues Encountered

- Plan frontmatter referenced `depth_chart_order` column in rosters — that column does not exist. Flagged in PLACEHOLDER-INVENTORY; 64-02 will use `snap_pct` ordering for starter selection.
- Data audit revealed **no** 2026 parquet files anywhere in the pipeline. Every endpoint in the contract must degrade to the latest 2025 snapshot.

## Next Phase Readiness

- **64-02 (rosters + current-week backend):** Contract fully specified. Paste Pydantic schemas into `web/api/models/schemas.py`, create `web/api/routers/teams.py` + `web/api/services/team_service.py`, implement fallback matrix.
- **64-03 (defense-metrics backend):** Contract fully specified. Same service file can host defense-metrics endpoint. Use corrected rating formula.
- **64-04 (frontend wiring):** Contract fully specified. Replace `buildDefensiveRoster` with fetch from Endpoint B `side=defense`, OL slots in `buildOffensiveRoster` from Endpoint B `side=offense`, seed `useState` from Endpoint A, and augment `MatchupAdvantages` tooltips with `positional.rank` from Endpoint C response.
- **Blocker for production:** 2026 bronze schedules/rosters must be ingested before the endpoints return real (non-fallback) data. This is an ingestion-pipeline task, not a Phase 64 blocker.

---
*Phase: 64-matchup-view-completion*
*Completed: 2026-04-17*

## Self-Check: PASSED

Verified:
- `PLACEHOLDER-INVENTORY.md` exists at `.planning/phases/64-matchup-view-completion/PLACEHOLDER-INVENTORY.md` (136 lines, 5 placeholder rows, Data Availability section, Summary Table present)
- `API-CONTRACT.md` exists at `.planning/phases/64-matchup-view-completion/API-CONTRACT.md` (414 lines, 3 endpoints, Pydantic block, Fallback matrix)
- Task 1 commit `c7c02a1` present in `git log --oneline`
- Task 2 commit `cab57ca` present in `git log --oneline`
- All 4 automated verify checks (task 1): `buildDefensiveRoster` (5), `MTCH-02` (3), `MTCH-04` (3), `2026` (20) — all > 0
- All 5 automated verify checks (task 2): `/api/teams/current-week` (4), `/api/teams/{team}/roster` (4), `/api/teams/{team}/defense-metrics` (5), `PositionalDefenseRank` (4), `Fallback` (1) — all > 0
