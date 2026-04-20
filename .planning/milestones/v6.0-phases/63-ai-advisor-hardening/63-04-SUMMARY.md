---
phase: 63-ai-advisor-hardening
plan: 04
subsystem: api
tags: [advisor, ai-tool, position-rankings, gold-layer, data-as-of, latest-week]

# Dependency graph
requires:
  - phase: 63-ai-advisor-hardening
    provides: TOOL-AUDIT baseline and empty-envelope contracts from 63-01 and 63-02
provides:
  - Backend `/api/projections/latest-week?season=<N>` endpoint that scans Gold parquet week partitions and returns `{season, week, data_as_of}` with HTTP 200 (week=null during offseason)
  - `ProjectionResponse.meta` Pydantic block carrying `{season, week, data_as_of, source_path}` for upstream traceability
  - `projection_service.get_projection_meta` + `get_latest_week` service functions that never raise (DB path returns null, offseason path returns null)
  - Frontend `web/frontend/src/lib/week-context.ts` `resolveDefaultWeek(season)` helper with 60s per-season cache
  - `getPositionRankings` tool now accepts optional `week`; auto-resolves via latest-week endpoint; surfaces `resolved_week`, `resolved_week_auto`, and `data_as_of` in the tool response
  - Structured `found: false` path with clear "check back Tuesday" message when Gold data is empty (no more silent mis-fires)
  - 10 contract tests in `tests/web/test_position_rankings_contract.py` pinning the Gold-layer grounding contract
affects:
  - 63-05 (ship gate re-audit will see getPositionRankings still PASS + new tool response fields)
  - Future projection tools: meta.data_as_of pattern can extend to `getPlayerProjection`, `compareStartSit`

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ProjectionMetaInfo dataclass — frozen service-layer DTO carrying parquet mtime + relative source path; propagates into the router's Pydantic ProjectionMeta without duplicating field definitions"
    - "Never-raise meta lookup — `get_projection_meta`/`get_latest_week` return typed objects with null fields rather than raising, so routers don't have to try/except two paths"
    - "Per-season 60s LRU-style cache on frontend helpers — keeps a chat turn's multiple tool calls from hammering /api/projections/latest-week while still reflecting Tuesday pipeline reruns within one minute"

key-files:
  created:
    - tests/web/test_position_rankings_contract.py
    - web/frontend/src/lib/week-context.ts
    - .planning/phases/63-ai-advisor-hardening/deferred-items.md
  modified:
    - web/api/models/schemas.py
    - web/api/routers/projections.py
    - web/api/services/projection_service.py
    - web/frontend/src/app/api/chat/route.ts

key-decisions:
  - "Optional `week` in tool schema — Zod `.optional()` rather than `.default(1)` so the LLM cannot silently pre-fill a wrong value; the presence/absence of `week` is the signal"
  - "Auto-resolution uses a separate `/latest-week` endpoint (not piggybacked on `/api/projections`) so the advisor can ask for scaffolding before committing to a full projection read — cheaper when preseason data is missing"
  - "Backend meta block is optional on `ProjectionResponse` — keeps backward compatibility for any consumer that doesn't expect it (Railway Parquet fallback path already shipped 2026-04-17)"
  - "Frontend helper returns `null` on fetch failure (distinct from `{week: null}`) so the advisor can distinguish 'season has no data' from 'backend unreachable'"
  - "Prefer `result.data.meta.data_as_of` over the latest-week helper's value — the meta block is closer to the actual projection read and guaranteed to agree with the rows we just returned"

patterns-established:
  - "Upstream traceability on Gold responses — any Gold-layer endpoint should expose `meta.data_as_of` (ISO 8601 UTC) so the advisor can cite data freshness without scraping filenames"
  - "Offseason tolerance via HTTP 200 + nullable week — endpoints that serve seasonal data now consistently return 200 with null fields rather than 404, matching the 63-02 empty-envelope pattern"
  - "Contract tests asserting both data shape AND semantic quality — `test_projected_points_are_positive_floats` + `test_projections_sorted_descending` would catch a hallucinated or inverted response that an OpenAPI schema check would miss"

requirements-completed: [ADVR-02]

# Metrics
duration: 15min
completed: 2026-04-19
---

# Phase 63 Plan 04: AI Advisor Top-N Gold Grounding Summary

**getPositionRankings is now grounded in the Gold layer with auto-resolved default week and ISO 8601 `data_as_of` traceability — the advisor can answer "who are the top 10 RBs" with real projected_points from the latest parquet, never fabricated numbers.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-19T19:43:00Z
- **Completed:** 2026-04-19T19:58:00Z
- **Tasks:** 2
- **Files created:** 3
- **Files modified:** 4

## Accomplishments

- `GET /api/projections/latest-week?season=2026` live against local backend: returns `{season:2026, week:1, data_as_of:"2026-04-10T23:28:50.289363+00:00"}`
- `GET /api/projections?position=RB&limit=10&season=2026&week=1` now includes a `meta` block with `{season, week, data_as_of, source_path}` pointing at `data/gold/projections/season=2026/week=1/projections_standard_20260410_192850.parquet`
- Empty-season probe: `GET /api/projections/latest-week?season=1999` returns HTTP 200 with `{season:1999, week:null, data_as_of:null}` — zero 404s during offseason queries
- Advisor `getPositionRankings` tool in `web/frontend/src/app/api/chat/route.ts`: `week` is now optional; when omitted the frontend calls `resolveDefaultWeek(season)` and flags the response with `resolved_week_auto:true`; response carries `data_as_of` the AI can cite verbatim
- 10 contract tests pinning Gold-layer grounding — includes the 6 originally specified in the plan (HTTP 200, list length, positive floats, descending sort, position filter, meta.data_as_of) plus 4 additional tests for the latest-week endpoint and meta round-trip
- Full local audit re-run: 7 PASS / 5 WARN / 0 FAIL against `http://127.0.0.1:8000` — `getPositionRankings` still PASS, no regression in the other 11 tools

## Resolved Week for Season 2026

Per the plan's Output section:
- **latest-week result:** `{season: 2026, week: 1, data_as_of: "2026-04-10T23:28:50.289363+00:00"}`
- **Gold coverage:** Only week=1 currently has parquet files in `data/gold/projections/season=2026/`; once week=2 lands the endpoint will auto-promote
- **Edge case:** No `week=0` preseason directory exists in the current layout (file is under `data/gold/projections/preseason/season=2026/`, a different tree); auto-resolution correctly picks `week=1`

## Example Advisor Tool Response (season=2026, no week specified)

```json
{
  "found": true,
  "position": "RB",
  "scoring_format": "half_ppr",
  "season": 2026,
  "week": 1,
  "resolved_week": 1,
  "resolved_week_auto": true,
  "data_as_of": "2026-04-10T23:28:50.289363+00:00",
  "rankings": [
    {"rank": 1, "player_name": "Saquon Barkley",  "team": "PHI", "projected_points": 381.0, ...},
    {"rank": 2, "player_name": "Jahmyr Gibbs",    "team": "DET", "projected_points": 355.2, ...},
    {"rank": 3, "player_name": "Derrick Henry",   "team": "BAL", "projected_points": 338.6, ...}
  ]
}
```

The `resolved_week_auto: true` flag tells the AI the week was back-filled automatically so it can phrase its reply as "based on the latest available projections (week 1 of 2026, refreshed April 10)…" rather than asserting a week the user never specified.

## Task Commits

1. **Task 1 (TDD RED):** `0d6fb3c` — test(63-04): add position rankings contract — Gold-layer grounding (6 assertions, test_meta_data_as_of skipped pending Task 2)
2. **Task 2 (backend GREEN):** `925c8d7` — feat(63-04): add meta.data_as_of + /api/projections/latest-week (ProjectionMeta + LatestWeekResponse + service helpers + 4 additional contract tests; skip flipped to pass)
3. **Task 2 (frontend GREEN):** `dedc9e2` — feat(63-04): advisor auto-resolves default week + surfaces data_as_of (resolveDefaultWeek helper + getPositionRankings tool update + structured found:false)
4. **Task 2 documentation:** `c4c93eb` — docs(63-04): log pre-existing test_external_rankings failures (out-of-scope 63-03 failures deferred)

Plan metadata commit will follow after STATE.md + ROADMAP.md updates.

## Files Created/Modified

### Created
- `tests/web/test_position_rankings_contract.py` — 10 contract tests: 6 core plus latest-week endpoint coverage + meta round-trip
- `web/frontend/src/lib/week-context.ts` — `resolveDefaultWeek(season)` + `clearLatestWeekCache()` with 60s per-season cache
- `.planning/phases/63-ai-advisor-hardening/deferred-items.md` — pre-existing 63-03 test_external_rankings failures logged

### Modified
- `web/api/models/schemas.py` — added `ProjectionMeta` model, attached `meta: Optional[ProjectionMeta]` to `ProjectionResponse`, added `LatestWeekResponse` model
- `web/api/routers/projections.py` — populate meta on every projection response; new `/latest-week` endpoint scans `season=<N>/week=*/` for highest week
- `web/api/services/projection_service.py` — added `ProjectionMetaInfo` dataclass, `get_projection_meta(season, week)`, `get_latest_week(season)`, `_iso_utc`, `_project_relative`
- `web/frontend/src/app/api/chat/route.ts` — `getPositionRankings` tool: week optional, auto-resolve path, `resolved_week`/`resolved_week_auto`/`data_as_of` in response, structured `found: false` on empty Gold data, updated tool description to instruct the LLM to omit `week` for "top 10" style queries

## Decisions Made

See frontmatter `key-decisions`. Summary: `week` becomes `Optional` (not `default(1)`) so the LLM cannot silently fabricate; a dedicated `/latest-week` endpoint is cheaper than piggybacking on `/api/projections`; meta is additive to keep deployed Railway Parquet-fallback compatibility; frontend helper distinguishes "no data" from "backend unreachable".

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Scope] Black reformatter swept unrelated files**
- **Found during:** Task 2 (pre-commit Python formatting)
- **Issue:** Running `black web/api/` to normalize the two edited files also reformatted `web/api/services/external_rankings_service.py`, `web/api/services/prediction_service.py`, `web/api/main.py`, and `web/api/routers/rankings.py` (plan 63-03 scope, not 63-04).
- **Fix:** Reverted the unrelated reformat via `git checkout --` and only staged the files directly modified by plan 63-04.
- **Files modified:** none (reverted)
- **Verification:** `git status --short` showed only the plan-63-04 files staged before commit.
- **Committed in:** n/a (preserved scope boundary rather than committing the sweep)

**2. [Rule 3 — Scope] Extended the contract test from 6 to 10 cases**
- **Found during:** Task 2 (backend verification)
- **Issue:** Plan specified 6 assertions; the new `/latest-week` endpoint and meta round-trip had no coverage.
- **Fix:** Appended 4 tests (latest-week happy path, highest-week ordering, empty-season 200 with nulls, meta season/week round-trip). All green.
- **Files modified:** `tests/web/test_position_rankings_contract.py`
- **Verification:** 10/10 pass; full `tests/test_web_api.py + tests/web/*` suite at 35/35 pass with no regressions.
- **Committed in:** `925c8d7` (Task 2 backend commit)

---

**Total deviations:** 2 scope-management decisions (kept scope tight, added tests for new surface). No functional deviations from the plan.
**Impact on plan:** No scope creep. The extra 4 tests cover endpoints the plan itself added and strengthen the Gold-grounding contract the plan explicitly demands.

## Issues Encountered

- `tests/web/test_external_rankings.py` has 6 failing tests that predate plan 63-04 (plan 63-03 staged the test file, service layer envelope never implemented). Logged to `deferred-items.md` for a 63-03 wrap-up plan; none block ADVR-02.
- Pre-commit hook reformatted multiple files outside plan 63-04 scope (see deviation 1). Reverted to preserve scope hygiene.
- Next.js `tsc --noEmit` reports one pre-existing type error in `web/frontend/src/components/file-uploader.tsx` (missing `formatBytes` export in `@/lib/utils`). Unrelated; no impact on plan-63-04 files which compile cleanly.

## Known Stubs

None. `getPositionRankings` now binds to real Gold data or returns a structured "not yet" message. No placeholder strings, no mock data in the response path.

## Threat Flags

None. Changes are additive: new read-only endpoint + response fields. No new auth paths, no new trust boundaries, no schema changes affecting permissions.

## User Setup Required

None — the new `/api/projections/latest-week` endpoint requires no configuration and will deploy automatically on the next Railway image build once this commit is pushed.

## Next Phase Readiness

- **63-05 (ship gate re-audit):** Unblocked. The audit probe confirms `getPositionRankings` still PASS locally; once Railway picks up these commits, the re-audit on the live site should reproduce 7 PASS / 5 WARN / 0 FAIL.
- **Future extension:** The `meta.data_as_of` pattern is ready to propagate to `getPlayerProjection`, `compareStartSit`, and `getTeamRoster` with minimal additional code — just add the `meta=ProjectionMeta(...)` population to their respective routers.
- **ADVR-02 satisfied:** asking "who are the top 10 RBs" now returns 10 real RBs sorted by Gold-layer `projected_points`, with `data_as_of` the AI can cite. The plan's success criterion is met.

## Self-Check

- `tests/web/test_position_rankings_contract.py` → FOUND (10 tests, all pass)
- `web/frontend/src/lib/week-context.ts` → FOUND (52 lines)
- `.planning/phases/63-ai-advisor-hardening/deferred-items.md` → FOUND
- Commit `0d6fb3c` (test: contract tests RED) → FOUND
- Commit `925c8d7` (feat: meta + latest-week backend) → FOUND
- Commit `dedc9e2` (feat: frontend auto-resolve + data_as_of) → FOUND
- Commit `c4c93eb` (docs: deferred items) → FOUND
- `/api/projections/latest-week?season=2026` returns 200 with resolved week=1 → VERIFIED (uvicorn local curl)
- `/api/projections` response includes `meta.data_as_of` → VERIFIED (uvicorn local curl)
- Audit script still shows 7 PASS / 5 WARN / 0 FAIL — no regression → VERIFIED

## Self-Check: PASSED

---
*Phase: 63-ai-advisor-hardening*
*Completed: 2026-04-19*
