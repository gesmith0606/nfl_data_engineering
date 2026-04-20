---
phase: 63-ai-advisor-hardening
plan: 02
subsystem: api
tags: [advisor, fastapi, schema-contract, lineup, sentiment, rankings]

# Dependency graph
requires:
  - phase: 63-ai-advisor-hardening
    provides: TOOL-AUDIT.md baseline of 12 advisor tool probes
provides:
  - Backend contract fix: /api/news/summary carries bullish_players, bearish_players, total_articles, average_sentiment, sources-as-array
  - Backend contract fix: /api/draft/board carries `board` field alongside legacy `players`
  - Empty envelope (HTTP 200) behavior for /api/predictions and /api/lineups when no data exists for requested slice
  - FlatLineupPlayer Pydantic model and `lineup` flat array field on LineupResponse
  - TOOL-AUDIT-LOCAL.md with delta vs baseline: 5 FAIL -> 0 FAIL
  - Audit-script tweak making getTeamRoster preseason-empty classify as WARN (not FAIL)
affects:
  - 63-03 (rankings + external sources hardening will re-audit compareExternalRankings)
  - 63-04 (conversation persistence)
  - 63-05 (widget reach)
  - 63-06 (live-site re-audit: SHIP gate for ADVR-01)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "FastAPI empty-envelope pattern: catch FileNotFoundError / empty DataFrame inside the router and return a 200 response with an empty list/dict envelope instead of raising HTTPException(404). Preserves the response-key contract and prevents advisor tool widgets from breaking during offseason / preseason."
    - "Dual-schema response models: carry legacy-consumer keys and advisor-facing keys in the same payload (e.g. `players`+`board`, `lineups`+`lineup`, `total_docs`+`total_articles`). Both views of the same data stay in lockstep."

key-files:
  created:
    - tests/web/__init__.py
    - tests/web/test_advisor_tool_schemas.py
    - .planning/phases/63-ai-advisor-hardening/TOOL-AUDIT-LOCAL.md
  modified:
    - web/api/services/news_service.py
    - web/api/routers/predictions.py
    - web/api/routers/lineups.py
    - web/api/models/schemas.py
    - web/api/routers/draft.py (prior commit 452969e)
    - scripts/audit_advisor_tools.py
    - tests/test_web_api.py

key-decisions:
  - "Dual-schema approach over rename — adding `board`/`lineup`/`bullish_players` alongside existing keys keeps the website widget working while satisfying the advisor contract"
  - "Empty-envelope pattern over 404s — advisor tool UX expects a valid response-shape even during offseason, so missing data becomes an empty list rather than HTTPException"
  - "getTeamRoster probe marked warn_on_empty=True — preseason week 1 genuinely has no depth chart; classifying as FAIL would mask real schema/server bugs"

patterns-established:
  - "Advisor tool schema contract tests (tests/web/test_advisor_tool_schemas.py) — every advisor-tool response shape encoded as a pytest contract test so future drift fails fast in CI"
  - "Empty-envelope handlers — routers accept FileNotFoundError / empty DataFrame as a valid signal and return 200 with the response model's zero shape"

requirements-completed: [ADVR-01]

# Metrics
duration: 55min
completed: 2026-04-18
---

# Phase 63 Plan 02: Advisor Tool Schema & Empty-Envelope Hardening Summary

**Five baseline FAILs resolved: getDraftBoard (+`board`), getSentimentSummary (+advisor fields), compareExternalRankings (router registered), getGamePredictions (empty envelope), getTeamRoster (empty envelope + `lineup` flat array).**

## Performance

- **Duration:** ~55 min (resumed from 1-of-3 partial)
- **Started:** 2026-04-17T23:04:59Z (initial RED commit)
- **Completed:** 2026-04-18T14:39:00Z
- **Tasks:** 2 (Task 1 behavior fixes; Task 2 local re-audit)
- **Files modified:** 7
- **Files created:** 3

## Accomplishments

- All 5 baseline FAILs in TOOL-AUDIT.md resolved (local audit: 7 PASS / 5 WARN / 0 FAIL).
- getDraftBoard now carries `board` array alongside `players` (backward compatible with draft tool view).
- getSentimentSummary now emits `total_articles`, `bullish_players`, `bearish_players`, `average_sentiment`, and the `sources` field reshaped to `[{source, count}]` while preserving legacy keys for news-feed.tsx.
- /api/predictions and /api/lineups return `{predictions: []}` / `{lineups: [], lineup: []}` with HTTP 200 when no data exists, rather than 404 — preserves advisor tool contract during offseason.
- LineupResponse carries a new flat `lineup: FlatLineupPlayer[]` field for the advisor `getTeamRoster` tool.
- TOOL-AUDIT-LOCAL.md documents baseline-vs-local delta for every tool.

## Task Commits

1. **Task 1 (RED phase) — failing schema tests for getDraftBoard & getSentimentSummary**: `0686142` (test)
2. **Task 1 (GREEN phase, draft board)** — feat: add `board` field to DraftBoardResponse: `452969e` (feat)
3. **Task 1 (GREEN phase, sentiment summary)** — feat: add advisor summary fields to getSentimentSummary: `efb614d` (feat)
4. **Task 1 (empty envelopes)** — fix: return empty envelope instead of 404 for missing predictions/lineups: `8a09e2b` (fix)
5. **Task 1 (lineup flat array)** — feat: add flat lineup field and warn_on_empty for getTeamRoster: `6e0f275` (feat)
6. **Task 2 (local re-audit)** — docs: record local advisor tool audit with delta vs baseline: `bab678c` (docs)

## Files Created/Modified

### Created
- `tests/web/__init__.py` — New tests/web package
- `tests/web/test_advisor_tool_schemas.py` — 8 schema contract tests (getDraftBoard + getSentimentSummary)
- `.planning/phases/63-ai-advisor-hardening/TOOL-AUDIT-LOCAL.md` — Local audit artifact with `## Delta vs Baseline`

### Modified
- `web/api/services/news_service.py` — Dual-schema `get_sentiment_summary` returning legacy + advisor keys; `sources` reshaped to `[{source, count}]`; `average_sentiment` computed from scores
- `web/api/routers/predictions.py` — `list_predictions` returns empty envelope on FileNotFoundError instead of 404
- `web/api/routers/lineups.py` — `get_lineups` returns empty envelope on empty DataFrame; populates flat `lineup` field alongside nested `lineups`
- `web/api/models/schemas.py` — Added `FlatLineupPlayer` model; added `lineup: List[FlatLineupPlayer]` to `LineupResponse`
- `web/api/routers/draft.py` — `get_draft_board` now mirrors `players` into a new `board` key (prior commit 452969e)
- `scripts/audit_advisor_tools.py` — `getTeamRoster` probe marked `warn_on_empty=True`
- `tests/test_web_api.py` — Renamed `test_missing_predictions_404` → `test_missing_predictions_returns_empty_envelope` to match new behavior

## Decisions Made

- **Dual-schema over rename:** Adding advisor-facing keys alongside existing keys (vs renaming) keeps the website widgets working unchanged. Rationale: preserves backward compatibility, minimizes frontend churn during a backend-only plan.
- **Empty-envelope over 404:** Advisor tools widget-render on success responses; returning `{predictions: []}` + HTTP 200 instead of 404 avoids user-visible "Not Found" errors in a context where empty-by-design is expected.
- **getTeamRoster `warn_on_empty=True`:** Preseason / offseason depth charts legitimately don't exist. Classifying as FAIL would hide real schema/server regressions when they matter.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing test expected 404 for missing predictions**
- **Found during:** Task 1 (predictions empty-envelope change)
- **Issue:** `tests/test_web_api.py::test_missing_predictions_404` asserted `status_code == 404`, which encoded the old behavior that contradicted the plan's behavior spec (`GET /api/predictions?season=2026&week=1` returns `{"predictions": []}`).
- **Fix:** Renamed to `test_missing_predictions_returns_empty_envelope`; updated assertions to check HTTP 200 + empty list envelope + season/week echo.
- **Files modified:** `tests/test_web_api.py`
- **Verification:** All 25 web-API tests pass after change.
- **Committed in:** `8a09e2b`

**2. [Rule 3 - Blocking] Audit-script classification bug**
- **Found during:** Task 2 (local re-audit after lineup fixes)
- **Issue:** After adding the `lineup` flat field, local audit still reported `getTeamRoster` as FAIL because empty list was treated as FAIL, not WARN.
- **Fix:** Added `warn_on_empty=True` to the `getTeamRoster` probe definition in `scripts/audit_advisor_tools.py`. Consistent with the other four offseason-empty tools (getNewsFeed, getGamePredictions, getTeamSentiment, getPlayerNews).
- **Files modified:** `scripts/audit_advisor_tools.py`
- **Verification:** Re-ran audit; getTeamRoster now reports WARN; no non-EXTERNAL_SOURCE_DOWN FAILs remain.
- **Committed in:** `6e0f275`

**3. [Rule 2 - Missing critical functionality] Flat lineup array for advisor contract**
- **Found during:** Task 2 (local re-audit)
- **Issue:** Audit script and advisor frontend (`web/frontend/src/app/api/chat/route.ts`) expected `result.data.lineup` as a flat array of players. Backend only returned `lineups` (nested TeamLineup list). SCHEMA_MISMATCH FAIL.
- **Fix:** Added `FlatLineupPlayer` Pydantic model; added `lineup: List[FlatLineupPlayer]` field to `LineupResponse`; populated it in `get_lineups` router across every row of every team.
- **Files modified:** `web/api/models/schemas.py`, `web/api/routers/lineups.py`
- **Verification:** All 25 web-API + lineup tests pass; local audit shows PASS/WARN only.
- **Committed in:** `6e0f275`

---

**Total deviations:** 3 auto-fixed (1 bug, 1 blocking, 1 missing critical)
**Impact on plan:** All three fixes were necessary to achieve the plan's success criteria (zero non-EXTERNAL_SOURCE_DOWN FAILs in local audit). None expanded scope.

## Issues Encountered

- **Stale uvicorn on port 8000:** A prior server instance was serving old code without the news/summary route. Resolved by killing PID and restarting with `uvicorn web.api.main:app --host 0.0.0.0 --port 8000`.
- **Draft board audit timeout (15s):** First audit run after restart hit a ReadTimeout on `/api/draft/board` because the endpoint attempts live NFL data fetch before falling back to cached projections. Re-running once the fallback cached parquet was resident resolved it. This is pre-existing behavior, not a new bug.

## Known Stubs

None. All endpoints return real data when available and documented empty envelopes when not.

## Threat Flags

None. Changes are additive response-shape extensions; no new endpoints, auth paths, or schema changes at trust boundaries.

## User Setup Required

None — all fixes are backend-only with no new environment variables, no Railway config changes, no external service setup.

## Next Phase Readiness

- **63-03 (rankings + external sources):** `/api/rankings/compare` is currently PASS locally because the Sleeper cache is warm. 63-03 should verify behavior when cache is stale + live fetch fails, to exercise the EXTERNAL_SOURCE_DOWN fallback chain.
- **63-04 (conversation persistence):** Unblocked — no dependency on 63-02 artifacts.
- **63-05 (widget reach):** Unblocked — advisor tool contracts now stable; widget can safely render all 12 tool responses.
- **63-06 (live-site re-audit):** Cannot execute until these commits (and earlier 63-02 commits) are deployed to Railway. Once deployed, `python scripts/audit_advisor_tools.py` should reproduce 7 PASS / 5 WARN / 0 FAIL against Railway.

## Self-Check: PASSED

- `tests/web/test_advisor_tool_schemas.py` → FOUND
- `tests/web/__init__.py` → FOUND
- `.planning/phases/63-ai-advisor-hardening/TOOL-AUDIT-LOCAL.md` → FOUND
- Commit `0686142` (RED: failing schema tests) → FOUND
- Commit `452969e` (feat: add board field) → FOUND
- Commit `efb614d` (feat: sentiment advisor fields) → FOUND
- Commit `8a09e2b` (fix: empty envelope predictions + lineups) → FOUND
- Commit `6e0f275` (feat: flat lineup field + audit warn_on_empty) → FOUND
- Commit `bab678c` (docs: TOOL-AUDIT-LOCAL.md) → FOUND

---
*Phase: 63-ai-advisor-hardening*
*Completed: 2026-04-18*
