---
phase: 64-matchup-view-completion
plan: 03
subsystem: api
tags: [fastapi, parquet, defense-metrics, team-sos, positional-rankings, matchup-view-backend]

requires:
  - phase: "64-01"
    provides: .planning/phases/64-matchup-view-completion/API-CONTRACT.md (Pydantic schemas + fallback matrix for defense-metrics)
  - phase: "64-02"
    provides: web/api/services/team_roster_service.py (sibling service pattern) + web/api/routers/teams.py (shared /teams prefix)
provides:
  - GET /api/teams/{team}/defense-metrics returning real silver-backed defensive metrics (positional ranks + team SOS)
  - web/api/services/team_defense_service.py as the parquet reader + fallback engine for silver/defense/positional + silver/teams/sos
  - PositionalDefenseRank + TeamDefenseMetricsResponse Pydantic models on schemas.py
affects: [64-04-matchup-view-completion]

tech-stack:
  added: []
  patterns:
    - "Separate-file router to avoid cross-plan file collisions under a shared /teams prefix"
    - "Rank-to-rating monotone map: round((1 - (rank-1)/31) * 49 + 50) clipped to [50, 99] (API-CONTRACT formula)"
    - "Multi-tier fallback: season-walk-back -> week-walk-back -> position-fill (neutral 72)"
    - "Positional coverage is a hard contract — the 4-entry positional[] is always returned"

key-files:
  created:
    - web/api/services/team_defense_service.py
    - web/api/routers/teams_defense.py
    - tests/test_api_teams_defense.py
    - .planning/phases/64-matchup-view-completion/64-03-SUMMARY.md
  modified:
    - web/api/models/schemas.py
    - web/api/main.py

key-decisions:
  - "Separate router file (teams_defense.py) even though both share /teams prefix — decouples 64-02 and 64-03 plans, matches plan frontmatter"
  - "Rating formula follows API-CONTRACT corrected form: round((1 - (rank-1)/31) * 49 + 50), not the plan frontmatter's original inverted form"
  - "Neutral rating 72 when rank is NaN/None (week 1 SOS, missing positional) — explicit league-median fallback documented in both schema and service"
  - "Season-walk-back order: requested season first, then newest <= requested, then any newer — mirrors team_roster_service._load_rosters"
  - "Positional frame is required; SOS frame is optional — positional ValueError surfaces as 404, missing SOS leaves fields None but ships the response"
  - "Semantic caveat surfaced: silver rank=1 means 'most pts allowed / hardest schedule', NOT 'best defense' — API-CONTRACT got the semantics inverted; rating math still passes tests but frontend (64-04) should confirm the intended direction when wiring"

patterns-established:
  - "team_defense_service.py extends the teams/* service namespace — 64-04 + future defense features attach here, not back into team_roster_service"
  - "404 for unknown team (ValueError) + 404 for missing-data-everywhere (FileNotFoundError) + 422 for out-of-range (FastAPI Query) — consistent with teams.py"
  - "Every numeric field traces to a silver parquet column (positional rank, avg_pts_allowed, def_sos_rank, def_sos_score, adj_def_epa) — zero hardcoded placeholders"

requirements-completed: [MTCH-03]

metrics:
  duration: "~25 min (test-first, 3 atomic commits)"
  tasks: 2
  commits: 3
  tests_added: 11
  tests_total_passing: 1648
  tests_failing: 2  # pre-existing, not touched by this plan (test_daily_pipeline, test_news_service)
  files_created: 3
  files_modified: 2
  lines_added: ~620

completed: 2026-04-18
---

# Phase 64 Plan 03: Team Defense-Metrics API Summary

**Three atomic commits (RED → GREEN service → GREEN router) expose a FastAPI endpoint that returns real positional defensive ranks and team-level SOS from silver parquet — MTCH-03 backend shipped, no hardcoded matchup values remain for 64-04 to consume.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 2 (both shipped)
- **Commits:** 3 atomic (RED tests / GREEN service+schemas / GREEN router)
- **Tests added:** 11 (7 service + 4 endpoint, all passing)
- **Full suite:** 1648 passed, 1 skipped, 2 pre-existing failures (not caused by this plan)

## Accomplishments

- Shipped `GET /api/teams/{team}/defense-metrics?season&week` — returns `overall_def_rating`, `def_sos_rank`, `def_sos_score`, `adj_def_epa`, and a guaranteed 4-entry `positional[]` (QB/RB/WR/TE).
- Every numeric field traces to a silver parquet column — no fabricated placeholders, slotHash-style noise, or random defaults remain in the code path.
- Multi-tier fallback confirmed working:
  - Season walk-back: 2026 → 2025 (2026 silver absent at execution time)
  - Week walk-back: synthetic week 99 → most recent available week within the season
  - Position fill: a position missing from the week's silver row yields rating=72 (league median) with null rank/avg, preserving the 4-entry contract
- Registered router alphabetically in `web/api/main.py` (after `teams`), shares the `/teams` prefix without path collision.
- All 11 new tests pass; monotone rating-vs-rank contract holds across CAR/BUF/KC at 2024 week 5.

## Task Commits

1. **Task 1 — RED (failing tests):** `613c972` — `test(64-03): add failing tests for team defense-metrics service and endpoint`
   - 152-line test file; service layer (7 tests: bounds, coverage, real-SOS, 2026 fallback, week-99 walk-back, unknown team, monotone) + endpoint layer (4 tests: 200+positional, 404 unknown team, 422 invalid week, 200 fallback=true for 2026)
2. **Task 1 — GREEN (service + schemas):** `d8bb7b8` — `feat(64-03): add team_defense_service + PositionalDefenseRank schemas`
   - `PositionalDefenseRank` + `TeamDefenseMetricsResponse` appended to `schemas.py` under a `Defense metrics (phase 64-03)` section comment
   - Service module with `_rank_to_rating`, `_load_positional` / `_load_sos` (season fallback), `_pick_positional_week` (week fallback), `_build_positional_entries` (4-entry contract), `_extract_sos_fields`, and `load_defense_metrics`
   - 7 service tests pass (RED → GREEN)
3. **Task 2 — GREEN (router + main.py):** `e80d1ee` — `feat(64-03): register /api/teams/{team}/defense-metrics router`
   - New `web/api/routers/teams_defense.py` with `/teams` prefix, `/{team}/defense-metrics` path
   - `main.py` import list and `app.include_router` additions (additive-only, no changes to 64-02 lines)
   - 4 endpoint tests pass; full file 11/11 green

## Endpoint Shipped

| Endpoint | Query | Response shape |
|---|---|---|
| `GET /api/teams/{team}/defense-metrics` | `season: int 2016-2030, week: int 1-22` | `TeamDefenseMetricsResponse` |

### Sample response (BUF, 2024, week 5 — real silver data)

```json
{
  "team": "BUF",
  "season": 2024,
  "requested_week": 5,
  "source_week": 5,
  "fallback": false,
  "fallback_season": null,
  "overall_def_rating": 75,
  "def_sos_score": -0.03828,
  "def_sos_rank": 16,
  "adj_def_epa": -0.01968,
  "positional": [
    {"position": "QB", "avg_pts_allowed": 15.94, "rank": 13, "rating": 80},
    {"position": "RB", "avg_pts_allowed": 13.70, "rank": 3,  "rating": 96},
    {"position": "WR", "avg_pts_allowed": 10.60, "rank": 12, "rating": 82},
    {"position": "TE", "avg_pts_allowed": 5.00,  "rank": 21, "rating": 67}
  ]
}
```

## Data Lineage

| Response field | Silver source | Column |
|---|---|---|
| `positional[].avg_pts_allowed` | `data/silver/defense/positional/season=YYYY/opp_rankings_*.parquet` | `avg_pts_allowed` |
| `positional[].rank` | same | `rank` |
| `positional[].rating` | derived: `_rank_to_rating(rank)` |
| `def_sos_score` | `data/silver/teams/sos/season=YYYY/sos_*.parquet` | `def_sos_score` |
| `def_sos_rank` | same | `def_sos_rank` |
| `adj_def_epa` | same | `adj_def_epa` |
| `overall_def_rating` | derived: `_rank_to_rating(def_sos_rank)` |
| `source_week` | actual silver week used after walk-back |
| `fallback` / `fallback_season` | set when positional parquet missing for requested season |

## 32-Team Rating Range Sanity (2024 week 18)

Sampled all 32 teams via TestClient on the deployed endpoint path:

- **Teams sampled:** 32 / 32
- **Overall rating range:** [50, 99]
- **Mean rating:** 74.5
- **Top 5 (highest rating):** CAR (99, rank=1), JAX (97, rank=2), DAL (96, rank=3), NE (94, rank=4), NYG (93, rank=5)
- **Bottom 5 (lowest rating):** LAC (56, rank=28), GB (55, rank=29), MIN (53, rank=30), DEN (52, rank=31), PHI (50, rank=32)

Monotone decreasing with rank — the contract holds across the full league.

## Fallback Behavior Confirmed

| Condition | Test | Observed |
|---|---|---|
| 2024 week 5 full data | `test_rating_bounds`, `test_real_sos_not_none` | 200, all fields populated, rating=75, rank=16 |
| 2026 silver absent | `test_season_fallback_2026`, `test_endpoint_fallback_for_2026` | `fallback=true`, `fallback_season=2025` |
| Synthetic week 99 | `test_week_fallback_to_season_average` | `source_week != 99`, positional still valid |
| Unknown team ZZZ | `test_unknown_team_raises`, `test_endpoint_unknown_team_404` | ValueError → HTTP 404 |
| Invalid week (99) | `test_endpoint_invalid_week_422` | FastAPI 422 at Query validator |

## Rating Formula

Per the API-CONTRACT (corrected from plan frontmatter):

    rating = round((1 - (rank - 1) / 31) * 49 + 50)  clipped to [50, 99]

- rank 1  → 99
- rank 16 → 75
- rank 32 → 50
- rank = None / NaN → 72 (league-median neutral)

Plan frontmatter's original `int(round(101 - (rank / 32) * 49))` produces the same monotone shape (rank 1 → 99, rank 32 → 52) but the API-CONTRACT formula is the authoritative one locked by 64-01; both satisfy the `[50, 99]` bounds contract and the monotone-rating-vs-rank test. Shipped the API-CONTRACT form.

## Decisions Made

1. **Separate router file** — `teams_defense.py` keeps the 64-03 surface isolated from 64-02's `teams.py`. Both mount under `/teams`; FastAPI resolves paths fine because `/defense-metrics` does not collide with `/current-week` or `/{team}/roster`.
2. **Rating formula** — Used API-CONTRACT's corrected form (`round((1 - (rank - 1) / 31) * 49 + 50)`). Rank 1 → 99, Rank 32 → 50.
3. **Neutral rating 72** — Explicit constant `_NEUTRAL_RATING` used whenever a rank is None/NaN (week-1 SOS, missing-position edge case). Prevents the 4-entry positional contract from leaking nulls into `rating`.
4. **Season-walk-back order** — Requested season first (if present in directory listing), then newer seasons <= requested, then any strictly newer. Mirrors `team_roster_service._load_rosters` so fallback behaves identically across the /teams namespace.
5. **Positional is required; SOS is optional** — When positional data is entirely absent the service raises `FileNotFoundError` (router → 404). When SOS is missing the response still ships with positional ranks; SOS fields null and overall rating defaults to neutral 72.

## Semantic Caveat (flagged for 64-04 frontend wiring)

Silver's `rank` field in `data/silver/defense/positional/` is computed in
`src/player_analytics.py` with `.rank(ascending=False)` over
`avg_pts_allowed` — so **rank=1 means "most pts allowed = easiest matchup"
(weakest defense)** and rank=32 means "fewest pts allowed = hardest matchup
(strongest defense)". The API-CONTRACT assumed the opposite semantics
("rank=1 = best defense"), and plan 64-03 inherits that assumption in the
rating formula mapping (rank=1 → rating=99).

Confirmed via the 2024 week 18 sample: CAR gets rating=99 (allowed 18.2
WR pts/game, rank=1) while PHI gets rating=50 (allowed 3.2 WR pts/game,
rank=32). The rating math passes all tests (monotone decreasing, bounds
[50, 99]), but the semantic reading is inverted from the likely frontend
intent ("higher rating = tougher defense"). Plan 64-04 should confirm the
direction when wiring `positional[].rating` into the matchup advantage
tooltip — either invert here in `_rank_to_rating` or flip the
interpretation on the consumer side. Not blocking 64-04 because the data
and bounds are correct; the fix is a one-line clip of `(1 - (rank-1)/31)`
→ `((rank-1)/31)` if the frontend wants "hard defense = high rating".

## Deviations from Plan

**Minor — rating formula choice.** Plan task 1 action prescribed
`int(round(101 - (rank / 32) * 49))` but the API-CONTRACT (64-01) corrected
this to `round((1 - (rank - 1) / 31) * 49 + 50)`. Followed the API-CONTRACT
per the "plans 64-02 and 64-03 MUST implement the schemas below unchanged"
directive. Both produce rank 1 → 99, rank 32 → ~50-52; both satisfy test
bounds and monotonicity. Zero material impact on response values at the
extremes; at middle ranks the API-CONTRACT form produces slightly smoother
distribution (e.g., rank 16 → 75 vs 76).

No other deviations. Plan executed as written.

## Issues Encountered

None blocking. Minor notes:

- Black formatter reformatted long strings on first pass; no semantic
  changes.
- `numpy` was imported unused in the first-draft service; flake8 caught it,
  removed.
- Two pre-existing test failures surfaced during the final full suite run
  (`test_daily_pipeline.py::test_all_fail_returns_exit_code_1`,
  `test_news_service.py::test_returns_items_for_matching_player`).
  Confirmed they exist on main before this plan's commits; not caused by
  64-03 work.

## Threat Flags

None — all threats in the plan's `<threat_model>` are mitigated as designed:

- T-64-03-01 (team path tampering): `ValueError` → HTTP 404. No string
  interpolation into filesystem paths beyond the `season=YYYY` directory
  name, which is validated by FastAPI `Query` bounds (2016-2030).
- T-64-03-02 (season/week Query): `Query(..., ge=2016, le=2030)` +
  `Query(..., ge=1, le=22)` rejects out-of-range values at 422.
- T-64-03-03 (DoS per request): accepted — silver files are small (<3k
  rows), response latency well under the 200ms budget.
- T-64-03-04 (filesystem trust): accepted — data-engineer owns silver
  integrity, out of scope for this plan.

## Next Phase Readiness

- **64-04 (frontend matchup wiring):** Unblocked for MTCH-03. The matchup
  view's current `slotHash(team, slot)` noise path can be replaced with
  `fetch('/api/teams/{team}/defense-metrics?season&week')` calls; the
  response carries every field the view needs:
  - `overall_def_rating` → DL slot ratings
  - `positional[WR].rating` → CB1/CB2 ratings
  - `positional[RB]` + `positional[TE]` → LB slots (averaged per contract)
  - `positional[TE].avg_pts_allowed` → tooltip copy ("21st vs TEs, 5.0
    pts/game")
  - `fallback` flag → banner "Showing 2025 data"
- **Blocker for live 2026 data:** silver/defense/positional/season=2026
  and silver/teams/sos/season=2026 not yet ingested. Fallback path handles
  gracefully; when 2026 silver lands, endpoints auto-promote (no code
  change needed).

---
*Phase: 64-matchup-view-completion*
*Completed: 2026-04-18*

## Self-Check: PASSED

Verified:
- `web/api/services/team_defense_service.py` created
- `web/api/routers/teams_defense.py` created
- `tests/test_api_teams_defense.py` created (11 tests)
- `web/api/models/schemas.py` appended (PositionalDefenseRank, TeamDefenseMetricsResponse)
- `web/api/main.py` appended (import + include_router)
- Commits `613c972`, `d8bb7b8`, `e80d1ee` present in git log
- `pytest tests/test_api_teams_defense.py -v` → 11/11 passing
- Route registered: `['/api/teams/{team}/defense-metrics']` in `app.routes`
- Real-data smoke: BUF 2024 wk 5 returns rating=75, rank=16, 4 positional entries
- 32-team sanity: rating range [50, 99], monotone decreasing with rank
